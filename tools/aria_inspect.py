#!/usr/bin/env python3
"""READ-ONLY inspection of the 'aria' seat — enumerate its closets (id · content · category · score),
surface the earlier smoke's write ('smoke: deployed-stack check') by content, and characterize the rest,
so a human can confirm EXACTLY which closet is synthetic BEFORE any retract. No writes, no deletes.
Same in-VPC harness/env as deployed_stack_smoke.py."""
from __future__ import annotations
import json, os, subprocess, sys

API = os.environ.get("NEOS_SMOKE_API_URL") or ""
SITE = os.environ.get("NEOS_SMOKE_SITE_URL") or ""
ADMIN = os.environ.get("NEOS_SMOKE_ADMIN_KEY") or ""
CLIENT = os.environ.get("NEOS_SMOKE_CLIENT", "neuraledge")
MEMPALACE = os.environ.get("MEMPALACE_DIR", "")
if not (API and SITE and ADMIN):
    sys.exit("set NEOS_SMOKE_API_URL/SITE_URL/ADMIN_KEY")
os.environ["CONVEX_SITE_URL"] = SITE
sys.path.insert(0, os.environ.get("NEURALOPS_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from runtime import memory as broker  # noqa: E402
_CRUN_ENV = {**os.environ, "CONVEX_SELF_HOSTED_URL": API, "CONVEX_SELF_HOSTED_ADMIN_KEY": ADMIN}

SEAT = "aria"
# Queries chosen to surface BOTH the smoke write and real Aria SDR memory, so we enumerate broadly.
QUERIES = ["smoke deployed-stack check verification test",
           "sales outreach SDR pipeline lead client",
           "conversation task decision meeting",
           "founding operator disaster recovery"]
SMOKE_MARKERS = ("smoke", "deployed-stack", "deployed stack")


def crun(ref, args):
    out = subprocess.run(["npx", "convex", "run", ref, json.dumps(args)], cwd=MEMPALACE,
                         env=_CRUN_ENV, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:300])
    return json.loads(out.stdout) if out.stdout.strip() else None


def main():
    pal = crun("palace/queries:getPalaceByClient", {"clientId": CLIENT})
    pid = pal.get("_id") if isinstance(pal, dict) else None
    print(f"== aria inspect → palaceId={pid} seat={SEAT} ==")
    if not pid:
        print("no palaceId"); return 1

    # RAW dump — NO id-filter, NO dedup suppression. Print every chunk + full keys, per query, so we can
    # reconcile the 3-vs-0 discrepancy and see whether chunks even carry a closetId to retract by.
    seen = {}   # closetId -> chunk (only for chunks that HAVE an id)
    nullid = 0
    for q in QUERIES:
        try:
            resp = broker.retrieve(pid, SEAT, q, k=8) or {}
            chunks = resp.get("chunks", [])
        except Exception as e:
            print(f"  retrieve('{q[:30]}…') FAILED: {e}"); continue
        print(f"\n-- query {q[:40]!r}: {len(chunks)} raw chunk(s), confidence={resp.get('confidence')} reason={resp.get('reason')}")
        for c in chunks:
            cid = c.get("id")
            keys = sorted(c.keys())
            print(f"     id={cid!r}  score={c.get('score')} cat={c.get('category')} keys={keys}")
            print(f"       text: {(c.get('text') or '')[:160]!r}")
            if cid:
                seen.setdefault(cid, c)
            else:
                nullid += 1

    print(f"\n== SUMMARY (read-only; NO delete) ==")
    print(f"  distinct closets WITH an id: {len(seen)}   chunks with NULL id (unretractable): {nullid}")
    smoke = [cid for cid, c in seen.items() if any(m in (c.get('text') or '').lower() for m in SMOKE_MARKERS)]
    print(f"  smoke-content matches (by id): {smoke}")
    print(f"  ⇒ retract ONLY a human-confirmed smoke id; if 0 ids or null-id chunks, do NOT delete — reconcile first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
