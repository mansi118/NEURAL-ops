#!/usr/bin/env python3
"""Live edge-auth + audit proof against a deployed Convex backend (self-hosted or cloud).

Companion to dogfish_acl_smoke.py (which proved memory-ACL cross-seat). This proves, LIVE:
 - E1/E3 edge-auth: a binding OVERWRITES requester identity; unknown/reserved/cross-tenant are
   refused. The resolver is acp/edge_auth; its resolve_binding seam is wired to the LIVE Convex
   resolveBinding (not a fixture).
 - #12 denialsByLayer over the live audit_events (+ recordExternalDenial unifies an edge denial).
 - #6 embeddingHealth live (expected degraded — embedder is Bedrock, account-blocked).

ENV: CONVEX_SELF_HOSTED_URL + CONVEX_SELF_HOSTED_ADMIN_KEY (for `npx convex run`), PALACE_ID,
     MEMPALACE_DIR (default ../Mempalace_NEOS), NEURALOPS_DIR (default this repo).
"""
import os, sys, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
NEURALOPS = os.environ.get("NEURALOPS_DIR", os.path.dirname(HERE))
MEMPALACE = os.environ.get("MEMPALACE_DIR", os.path.join(os.path.dirname(NEURALOPS), "Mempalace_NEOS"))
PALACE = os.environ.get("PALACE_ID")
sys.path.insert(0, NEURALOPS)
from acp.edge_auth import resolve_edge_identity, EdgeRejected  # noqa: E402


def crun(ref, args):
    """`npx convex run <ref> <json>` in the Mempalace dir; parse the JSON result robustly."""
    p = subprocess.run(["npx", "convex", "run", ref, json.dumps(args)],
                       cwd=MEMPALACE, env={**os.environ}, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        # find the largest JSON object/array in the output
        for chunk in (out, out.splitlines()[-1] if out.splitlines() else ""):
            try:
                return json.loads(chunk)
            except Exception:
                pass
        return out


results = []
def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' ' + detail) if detail else ''}")


def live_rb(mxid):
    r = crun("access/bindings:resolveBinding", {"mxid": mxid})
    return r if isinstance(r, dict) else None


HMAC_OK = lambda _inbound: True
def AS(mxid, tenant="neuraledge"):
    return {"mxid": mxid, "tenant_id": tenant}


def main():
    if not PALACE:
        print("FATAL: set PALACE_ID", file=sys.stderr); return 2

    # E1 — bind @alice -> aria (live), resolve it.
    crun("access/bindings:upsertSeatBinding",
         {"mxid": "@alice:neuraledge.org", "tenant_id": "neuraledge", "seat_id": "aria", "role": "member"})
    b = live_rb("@alice:neuraledge.org")
    check("E1 resolveBinding live", isinstance(b, dict) and b.get("seat_id") == "aria",
          f"-> {b.get('seat_id') if isinstance(b, dict) else b}")

    # E3 happy path — a forged user_id is OVERWRITTEN from the live binding.
    try:
        out = resolve_edge_identity({"from": {"actor": "anon"}, "user_id": "forged-victim"},
                                    as_context=AS("@alice:neuraledge.org"),
                                    verify_hmac=HMAC_OK, resolve_binding=live_rb)
        check("E3 identity overwritten (forged->bound aria)",
              out.get("user_id") == "aria" and out.get("_identity_provenance") == "edge_bound")
    except EdgeRejected as e:
        check("E3 identity overwritten (forged->bound aria)", False, e.reason)

    # E3 refusals — unknown / reserved-claim / cross-tenant, all denied_at_layer=edge.
    def expect_reject(name, inbound, ctx, sub):
        try:
            resolve_edge_identity(inbound, as_context=ctx, verify_hmac=HMAC_OK, resolve_binding=live_rb)
            check(name, False, "expected refusal")
        except EdgeRejected as e:
            check(name, sub in e.reason and e.audit.get("denied_at_layer") == "edge", f"({e.reason})")

    expect_reject("E3 unknown mxid refused", {}, AS("@ghost:neuraledge.org"), "unknown_user")
    expect_reject("E3 reserved claim refused", {"user_id": "_admin"}, AS("@alice:neuraledge.org"), "reserved")
    expect_reject("E3 cross-tenant refused", {}, AS("@alice:neuraledge.org", "other"), "cross_tenant")

    # #12 — denialsByLayer over the live audit (dogfish smoke produced convex_sot denials);
    # record an edge denial to prove the unified sink carries both layers.
    crun("access/mutations:recordExternalDenial",
         {"palaceId": PALACE, "deniedAtLayer": "edge", "neopId": "@evil:x",
          "reason": "reserved_identity_claimed_from_channel"})
    d = crun("access/queries:denialsByLayer", {"palaceId": PALACE})
    by = d.get("byLayer", {}) if isinstance(d, dict) else {}
    check("#12 denialsByLayer live (convex_sot + edge)",
          by.get("convex_sot", 0) >= 1 and by.get("edge", 0) >= 1, f"-> {by}")

    # #6 — embeddingHealth live (visibility; expected degraded with Bedrock blocked).
    h = crun("palace/queries:embeddingHealth", {"palaceId": PALACE})
    check("#6 embeddingHealth live (visible)",
          isinstance(h, dict) and "degraded" in h,
          f"-> degraded={h.get('degraded') if isinstance(h, dict) else '?'}, "
          f"provider={h.get('provider') if isinstance(h, dict) else '?'}")

    ok = all(results)
    print(f"\n{'ALL PASS — edge-auth + audit hold LIVE' if ok else 'FAILURES — live not proven'} "
          f"({sum(results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
