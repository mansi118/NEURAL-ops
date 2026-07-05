#!/usr/bin/env python3
"""Ranked-retrieval proof — the STRONG /mcp bar (GAP-1 acceptance shape), the one deployed_stack_smoke.py
does NOT earn (its retrieve check is graceful-empty-tolerant → proves "responds", not "ranks").

Here the bar is literal: a distinctive, obviously-synthetic CANARY fact must come back at **rank-1** on an
**oblique, low-lexical-overlap** query (the #30 case), non-empty, with its score reported so ABS_MIN can be
pinned from where the oblique hit actually lands. **graceful-empty = HARD FAIL.** Same in-VPC harness +
env as deployed_stack_smoke.py. Reusable as the GAP-1 memory.ts acceptance test (same artifact, two uses).

Also: a READ-ONLY collision check on the 'aria' smoke seat — is it a real populated seat (the Aria SDR NEop)
or throwaway? — so we know whether the earlier smoke wrote into production memory.

The canary is written into a DISPOSABLE, obviously-synthetic seat scope; if cleanup is missed it is
unmistakably a canary and safe to orphan.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time

API = os.environ.get("NEOS_SMOKE_API_URL") or ""
SITE = os.environ.get("NEOS_SMOKE_SITE_URL") or ""
ADMIN = os.environ.get("NEOS_SMOKE_ADMIN_KEY") or ""
CLIENT = os.environ.get("NEOS_SMOKE_CLIENT", "neuraledge")
MEMPALACE = os.environ.get("MEMPALACE_DIR", "")

if not (API and SITE and ADMIN):
    sys.exit("set NEOS_SMOKE_API_URL, NEOS_SMOKE_SITE_URL, NEOS_SMOKE_ADMIN_KEY")

os.environ["CONVEX_SITE_URL"] = SITE
sys.path.insert(0, os.environ.get("NEURALOPS_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from runtime import memory as broker  # noqa: E402

_CRUN_ENV = {**os.environ, "CONVEX_SELF_HOSTED_URL": API, "CONVEX_SELF_HOSTED_ADMIN_KEY": ADMIN}
PASS, FAIL = [], []

# --- obviously-synthetic canary, distinctive marker, disposable scope ---
CANARY = "CANARY-NEUOPS-7Z3Q"
CANARY_FACT = (f"{CANARY} :: the founding operator's disaster-recovery rendezvous point is "
               f"Hangar Forty-Four, and the fallback passphrase is mauve-zeppelin.")
SEAT = "zzz-ranked-canary-smoke"                       # disposable; not a real seat
NEAR = "what is the fallback passphrase?"              # high-overlap (easy)
OBLIQUE = "where does the team regroup after an outage?"  # low-overlap, semantic (the #30 case)


def crun(ref, args):
    out = subprocess.run(["npx", "convex", "run", ref, json.dumps(args)],
                         cwd=MEMPALACE, env=_CRUN_ENV, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return json.loads(out.stdout) if out.stdout.strip() else None


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  · ' + detail if detail else ''}")


def retrieve_until_canary(pid, query, tries=6, wait=5):
    """Retry to absorb async embedding: return (chunks, found_rank1_bool, top_score) once the canary is
    rank-1, else the last state. Distinguishes 'not indexed yet' (empty) from 'indexed but mis-ranked'."""
    chunks = []
    for _ in range(tries):
        chunks = (broker.retrieve(pid, SEAT, query, k=5) or {}).get("chunks", [])
        if chunks and CANARY in (chunks[0].get("text") or ""):
            return chunks, True, chunks[0].get("score")
        time.sleep(wait)
    top_score = chunks[0].get("score") if chunks else None
    return chunks, False, top_score


def main():
    print(f"== ranked-retrieval proof → SITE={SITE} client={CLIENT} seat={SEAT} ==")
    pal = crun("palace/queries:getPalaceByClient", {"clientId": CLIENT})
    pid = pal.get("_id") if isinstance(pal, dict) else None
    check("tenant → palaceId", bool(pid), f"palaceId={pid}")
    if not pid:
        return _summary()

    # ---- Part A: aria collision check (READ-ONLY) ----
    try:
        tw = broker.get_twin(pid, "aria")
        ar = (broker.retrieve(pid, "aria", "sales outreach SDR pipeline lead", k=5) or {}).get("chunks", [])
        looks_real = bool(tw) and ((tw.get("maturity") not in (None, "seed")) or len(ar) > 1)
        check("aria scope inspected (read-only)", True,
              f"twin={'present' if tw else 'none'} maturity={tw.get('maturity') if tw else '-'} "
              f"closets_visible={len(ar)} ⇒ {'⚠️ LOOKS LIKE A REAL SEAT' if looks_real else 'looks throwaway'}")
    except Exception as e:
        check("aria scope inspected", False, str(e))

    # ---- Part B: the STRONG ranked proof (disposable scope) ----
    try:
        w = broker.write(pid, SEAT, {"content": CANARY_FACT, "title": "ranked-proof canary"})
        check("canary write (palace_remember)", w.get("status") in ("ok", "partial", "noop"), f"status={w.get('status')}")
    except Exception as e:
        check("canary write", False, str(e)); return _summary()

    oblique_score = None
    for label, q in [("near-hit", NEAR), ("oblique", OBLIQUE)]:
        chunks, rank1, score = retrieve_until_canary(pid, q)
        check(f"{label}: NON-EMPTY (graceful-empty = HARD FAIL)", len(chunks) > 0, f"{len(chunks)} chunks")
        check(f"{label}: rank-1 == canary", rank1,
              f"top.score={score} top.text={((chunks[0].get('text') if chunks else '') or '')[:70]!r}")
        if label == "oblique":
            oblique_score = score

    # ABS_MIN guidance: pin it from where the OBLIQUE hit lands (per GAP-1 spec), not the near-hit.
    if oblique_score is not None:
        print(f"  INFO  pin ABS_MIN below the oblique landing: oblique rank-1 score = {oblique_score}")
    return _summary()


def _summary():
    print(f"== {len(PASS)} passed, {len(FAIL)} failed ==")
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
