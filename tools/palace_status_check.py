#!/usr/bin/env python3
"""READ-ONLY: palace_status → stats (DB-level closet counts) + embedding health, to explain the 0-retrieval
result. If the embedder is degraded, retrieval returns empty SILENTLY (the exact failure the code warns
about) — which would mean the 7/7 smoke's graceful retrieve check passed on a degraded embedder, and the
'/mcp responds' claim needs re-qualifying. Also getStats/embeddingHealth raw via admin. No writes/deletes."""
from __future__ import annotations
import json, os, subprocess, sys

API = os.environ.get("NEOS_SMOKE_API_URL") or ""
SITE = os.environ.get("NEOS_SMOKE_SITE_URL") or ""
ADMIN = os.environ.get("NEOS_SMOKE_ADMIN_KEY") or ""
CLIENT = os.environ.get("NEOS_SMOKE_CLIENT", "neuraledge")
MEMPALACE = os.environ.get("MEMPALACE_DIR", "")
if not (API and SITE and ADMIN):
    sys.exit("set env")
os.environ["CONVEX_SITE_URL"] = SITE
sys.path.insert(0, os.environ.get("NEURALOPS_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from runtime import memory as broker  # noqa: E402
_CRUN_ENV = {**os.environ, "CONVEX_SELF_HOSTED_URL": API, "CONVEX_SELF_HOSTED_ADMIN_KEY": ADMIN}


def crun(ref, args):
    out = subprocess.run(["npx", "convex", "run", ref, json.dumps(args)], cwd=MEMPALACE,
                         env=_CRUN_ENV, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return {"_error": out.stderr.strip()[:300]}
    return json.loads(out.stdout) if out.stdout.strip() else None


def main():
    pal = crun("palace/queries:getPalaceByClient", {"clientId": CLIENT})
    pid = pal.get("_id") if isinstance(pal, dict) else None
    print(f"== palace status → palaceId={pid} ==")
    if not pid:
        print("no palaceId"); return 1

    print("\n-- palace_status (as aria, via /mcp) --")
    try:
        st = broker._post("palace_status", pid, "aria", {})
        print("  stats     :", json.dumps(st.get("stats")))
        print("  embedding :", json.dumps(st.get("embedding")))
        print("  l0        :", (str(st.get("l0"))[:120]))
        print("  neop scope:", json.dumps(st.get("neop")))
    except Exception as e:
        print("  palace_status FAILED:", e)

    print("\n-- getStats (admin, raw) --")
    print("  ", json.dumps(crun("palace/queries:getStats", {"palaceId": pid})))
    print("\n-- embeddingHealth (admin, raw — is the embedder actually working?) --")
    print("  ", json.dumps(crun("palace/queries:embeddingHealth", {"palaceId": pid})))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
