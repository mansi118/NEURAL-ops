#!/usr/bin/env python3
"""End-to-end NEOS process test against a live MemPalace backend.

The FULL chain, not slices: a FORGED inbound is bound to a seat by edge-auth, the tenant NAME is
resolved to a palaceId (the gateway connective step), then the REAL NEOS broker (runtime/memory.py)
does live memory ops under that seat — write lands (seat-routed + audited), retrieve degrades
gracefully (embedder blocked, #6), and the broker classifies denials by layer (Gate C) live.
Companion to dogfish_acl_smoke (memory-ACL) + live_edge_audit_smoke (edge-auth/audit).

ENV (defaults assume the self-hosted local backend):
  CONVEX_SELF_HOSTED_URL (:3210) + admin key (read from ~/convex-run/.env-local) for `npx convex run`;
  CONVEX_SITE_URL (:3211) for the broker's /mcp calls; palace seeded with clientId 'neuraledge'.
"""
import os, sys, json, subprocess

NEURALOPS = os.environ.get("NEURALOPS_DIR", "/mnt/c/Users/LENOVO/Downloads/NeuralOPS")
MEMPALACE = os.environ.get("MEMPALACE_DIR", "/mnt/c/Users/LENOVO/Downloads/Mempalace_NEOS")
API = os.environ.get("CONVEX_SELF_HOSTED_URL", "http://127.0.0.1:3210")
SITE = os.environ.get("CONVEX_SITE_URL", "http://127.0.0.1:3211")


def _admin_key():
    if os.environ.get("CONVEX_SELF_HOSTED_ADMIN_KEY"):
        return os.environ["CONVEX_SELF_HOSTED_ADMIN_KEY"]
    p = os.path.expanduser("~/convex-run/.env-local")
    try:
        for line in open(p):
            if line.startswith("ADMIN_KEY="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


ENV = {**os.environ, "CONVEX_SELF_HOSTED_URL": API, "CONVEX_SELF_HOSTED_ADMIN_KEY": _admin_key()}
os.environ["CONVEX_SITE_URL"] = SITE  # the broker reads this for /mcp
sys.path.insert(0, NEURALOPS)
from acp.edge_auth import resolve_edge_identity, EdgeRejected  # noqa: E402
from runtime import memory as broker  # noqa: E402


def crun(ref, args):
    """`npx convex run <ref> <json>` against the admin endpoint; parse the JSON result."""
    p = subprocess.run(["npx", "convex", "run", ref, json.dumps(args)],
                       cwd=MEMPALACE, env=ENV, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    try:
        return json.loads(out)
    except Exception:
        for ln in reversed(out.splitlines()):
            try:
                return json.loads(ln)
            except Exception:
                pass
        return out


results = []
def check(name, ok, detail=""):
    results.append(bool(ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' ' + detail) if detail else ''}")


def main():
    TENANT_NAME, MXID = "neuraledge", "@alice:neuraledge.org"

    # 0. Provision a binding (live): @alice -> aria.
    crun("access/bindings:upsertSeatBinding",
         {"mxid": MXID, "tenant_id": TENANT_NAME, "seat_id": "aria", "role": "member"})

    # 1. EDGE-AUTH: a FORGED inbound is bound to the credential's seat (forge discarded).
    def live_rb(mxid):
        r = crun("access/bindings:resolveBinding", {"mxid": mxid})
        return r if isinstance(r, dict) else None
    try:
        ident = resolve_edge_identity(
            {"from": {"actor": "anon"}, "user_id": "forged-attacker"},
            as_context={"mxid": MXID, "tenant_id": TENANT_NAME},
            verify_hmac=lambda _i: True, resolve_binding=live_rb)
        seat = ident["user_id"]
        check("edge-auth: forged inbound bound to aria",
              seat == "aria" and ident.get("_identity_provenance") == "edge_bound", f"seat={seat}")
    except EdgeRejected as e:
        check("edge-auth: forged inbound bound to aria", False, e.reason)
        return 1

    # 2. GATEWAY connective step: tenant NAME -> palaceId (the broker keys on palaceId).
    pal = crun("palace/queries:getPalaceByClient", {"clientId": TENANT_NAME})
    palaceId = pal.get("_id") if isinstance(pal, dict) else None
    check("gateway: tenant 'neuraledge' -> palaceId", bool(palaceId), f"palaceId={palaceId}")
    if not palaceId:
        return 1

    # 3. BROKER WRITE live — the NEOS broker -> live SoT integration.
    w = broker.write(palaceId, seat, {"content": "E2E: NeuralEDGE chose Convex over Supabase.", "title": "e2e"})
    check("broker.write live (palace_remember)", w.get("status") in ("ok", "partial", "quarantined", "noop"),
          f"status={w.get('status')}")

    # 4. BROKER RETRIEVE live — graceful degrade (embedder blocked, the #6 fix).
    r = broker.retrieve(palaceId, seat, "what database did we choose", k=3)
    check("broker.retrieve graceful degrade (#6)",
          r.get("confidence") == "low" and "retrieval_unavailable" in (r.get("reason") or ""),
          f"reason={r.get('reason')}")

    # 5. BROKER denial classification — blank seat refused client-side (denied_at_layer=broker).
    try:
        broker.write(palaceId, "   ", {"content": "x"})
        check("broker denies blank seat (denied_at_layer=broker)", False)
    except broker.MemPalaceError as e:
        check("broker denies blank seat (denied_at_layer=broker)", "denied_at_layer=broker" in str(e))

    # 6. BROKER denial classification — a seat lacking 'remember' -> server 403 -> convex_sot.
    try:
        broker.write(palaceId, "neuralchat", {"content": "x"})
        check("broker classifies SoT denial (denied_at_layer=convex_sot)", False)
    except broker.MemPalaceError as e:
        check("broker classifies SoT denial (denied_at_layer=convex_sot)",
              "denied_at_layer=convex_sot" in str(e), str(e)[:70])

    # 7. AUDIT — the SoT denial(s) landed in the unified sink (#12).
    d = crun("access/queries:denialsByLayer", {"palaceId": palaceId})
    by = d.get("byLayer", {}) if isinstance(d, dict) else {}
    check("audit denialsByLayer has convex_sot (#12)", by.get("convex_sot", 0) >= 1, f"-> {by}")

    # 8. #6 — embeddingHealth surfaces the blocked embedder.
    h = crun("palace/queries:embeddingHealth", {"palaceId": palaceId})
    check("embeddingHealth degraded (Bedrock blocked)",
          isinstance(h, dict) and h.get("degraded") is True,
          f"reason={h.get('reason') if isinstance(h, dict) else '?'}")

    ok = all(results)
    print(f"\n{'ALL PASS — NEOS process holds end-to-end LIVE' if ok else 'FAILURES — E2E not clean'} "
          f"({sum(results)}/{len(results)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
