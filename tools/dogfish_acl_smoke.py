#!/usr/bin/env python3
"""Live cross-seat seat-isolation smoke against a deployed MemPalace (dogfish).

The one ACL proof offline CANNOT give: convex-test SIMULATES the /mcp dispatcher; this hits
the REAL one. Two seats, raw /mcp POSTs. Asserts cross-seat write AND read are DENIED, while
own-room write/read are ALLOWED — the live counterpart of the offline access.test.ts suite.

PREREQS (once, on the live deployment — see Mempalace_NEOS):
  npx convex deploy                 # deploy functions+schema to small-dogfish-433
  npm run seed:palace               # prints the palaceId
  npx tsx scripts/seedAccess.ts     # seeds neop_permissions from config/access_matrix.yaml

ENV (NOTE the endpoint — this is the #1 dogfish foot-gun):
  CONVEX_SITE_URL = https://<deployment>.convex.site   # HTTP-actions endpoint.
  This is NOT the same as CONVEX_URL / the .convex.cloud client URL the seed scripts use.

USAGE:
  CONVEX_SITE_URL=https://small-dogfish-433.convex.site \
      python3 tools/dogfish_acl_smoke.py --palace <palaceId> [--seat-a aria --seat-b recon]

Exit 0 iff every assertion passes. No deploy creds needed — only the live HTTP endpoint.
"""
from __future__ import annotations
import os, sys, json, argparse, urllib.request, urllib.error


def post(base: str, tool: str, palace: str, neop: str, params: dict):
    """Raw /mcp POST. Returns (http_status, parsed_body). Never raises on 4xx/5xx."""
    body = json.dumps({"tool": tool, "palaceId": palace, "neopId": neop, "params": params}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/mcp", data=body,
        headers={"Content-Type": "application/json", "X-Palace-Neop": neop},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def _is_denied(status, resp) -> bool:
    return status == 403 or (isinstance(resp, dict) and resp.get("status") == "error")


def _data(resp):
    return resp.get("data") if isinstance(resp, dict) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dogfish_acl_smoke")
    ap.add_argument("--palace", required=True, help="seeded palaceId")
    ap.add_argument("--seat-a", default="aria")
    ap.add_argument("--seat-b", default="recon")
    ap.add_argument("--wing", default="team", help="a wing both seats may write (from access_matrix.yaml)")
    a = ap.parse_args(argv)

    base = os.environ.get("CONVEX_SITE_URL") or os.environ.get("CONVEX_DEPLOYMENT_URL")
    if not base:
        print("FATAL: set CONVEX_SITE_URL to the live .convex.site endpoint "
              "(NOT the .convex.cloud client URL).", file=sys.stderr)
        return 2
    A, B = a.seat_a, a.seat_b
    results: list[bool] = []

    def expect(name, want_denied, status, resp):
        denied = _is_denied(status, resp)
        ok = denied if want_denied else (status == 200 and not denied)
        results.append(ok)
        verdict = "PASS" if ok else "FAIL"
        want = "DENY" if want_denied else "ALLOW"
        print(f"  [{verdict}] {name}: want {want}, HTTP {status}"
              + (f"  {resp.get('error','')}" if isinstance(resp, dict) and resp.get('error') else ""))
        return ok

    # Each seat creates its own (owner-stamped) room.
    sa, ra = post(base, "palace_create_room", a.palace, A, {"wingName": a.wing, "roomName": "smoke_a", "summary": "acl smoke"})
    sb, rb = post(base, "palace_create_room", a.palace, B, {"wingName": a.wing, "roomName": "smoke_b", "summary": "acl smoke"})
    room_a, room_b = _data(ra), _data(rb)
    print(f"seat {A} room_a={room_a}  (HTTP {sa})")
    print(f"seat {B} room_b={room_b}  (HTTP {sb})")
    if not room_a or not room_b:
        print("FATAL: room creation failed — check the palaceId, that seedAccess ran, and the wing exists.",
              file=sys.stderr)
        print("  responses:", ra, rb, file=sys.stderr)
        return 2

    closet = {"content": "acl smoke closet", "category": "task"}
    # The four-cell core: own = allow, cross-seat = deny, for both write and read.
    expect(f"{A} WRITE own room",        False, *post(base, "palace_add_closet", a.palace, A, {**closet, "roomId": room_a}))
    expect(f"{A} WRITE {B}'s room",      True,  *post(base, "palace_add_closet", a.palace, A, {**closet, "roomId": room_b}))
    expect(f"{A} READ own room",         False, *post(base, "palace_get_room",  a.palace, A, {"roomId": room_a}))
    expect(f"{A} READ {B}'s room",       True,  *post(base, "palace_get_room",  a.palace, A, {"roomId": room_b}))

    ok = all(results)
    print(f"\n{'ALL PASS — live seat isolation holds' if ok else 'FAILURES — live isolation NOT proven'} "
          f"({sum(results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
