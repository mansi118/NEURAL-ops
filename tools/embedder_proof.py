#!/usr/bin/env python3
"""Embedder proof — the acceptance gate for activation step 2 (embedder unblock).

UNLIKE the deployed-stack smoke (whose retrieve check tolerates graceful-empty — which is exactly why it
did NOT catch that the embedder was dead), this asserts REAL semantic retrieval: seed distinct documents,
query a paraphrase that shares NO content words with the target, and require the target back, RANKED, with
a non-empty chunk and a real score. An empty-but-graceful result is FAILURE here — the opposite of the smoke.

Run (in-VPC; Convex is internal):
  NEOS_SMOKE_API_URL=http://convex.<ns>:3210 NEOS_SMOKE_SITE_URL=http://convex.<ns>:3211 \
  NEOS_SMOKE_ADMIN_KEY=… python3 tools/embedder_proof.py
Exit 0 ⇔ the seeded target is retrieved by meaning.
"""
from __future__ import annotations
import os, sys, time

API = os.environ.get("NEOS_SMOKE_API_URL") or ""
SITE = os.environ.get("NEOS_SMOKE_SITE_URL") or ""
ADMIN = os.environ.get("NEOS_SMOKE_ADMIN_KEY") or ""
CLIENT = os.environ.get("NEOS_SMOKE_CLIENT", "neuraledge")
SEAT = os.environ.get("NEOS_SMOKE_SEAT", "_admin")  # full access — isolates the EMBEDDER from ACL/routing
MEMPALACE = os.environ.get("MEMPALACE_DIR", "/mnt/c/Users/LENOVO/Downloads/Mempalace_NEOS")

if not (API and SITE and ADMIN):
    sys.exit("set NEOS_SMOKE_API_URL, NEOS_SMOKE_SITE_URL, NEOS_SMOKE_ADMIN_KEY")

os.environ["CONVEX_SITE_URL"] = SITE
sys.path.insert(0, os.environ.get("NEURALOPS_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import subprocess, json  # noqa: E402
from runtime import memory as broker  # noqa: E402

_CRUN_ENV = {**os.environ, "CONVEX_SELF_HOSTED_URL": API, "CONVEX_SELF_HOSTED_ADMIN_KEY": ADMIN}

# Distinct docs. The query shares NO surface words with the target ("Eiffel"/"Seine"/"lattice" vs
# "monument"/"capital"/"France") — a hit can only come from the embedding space, not keyword overlap.
DOCS = [
    ("eiffel", "The Eiffel Tower is an iron lattice structure on the bank of the Seine; tourists ride it daily."),
    ("photo", "Chlorophyll lets green plants turn sunlight into sugars through photosynthesis."),
    ("compiler", "A just-in-time compiler translates bytecode into native machine instructions while a program runs."),
]
QUERY = "What is the most famous monument in the capital of France?"
TARGET_TOKEN = "Eiffel"   # distinctive to the target doc; absent from the query


def main():
    print(f"== embedder proof → API={API} client={CLIENT} seat={SEAT} ==")
    pal = subprocess.run(["npx", "convex", "run", "palace/queries:getPalaceByClient", json.dumps({"clientId": CLIENT})],
                         cwd=MEMPALACE, env=_CRUN_ENV, capture_output=True, text=True, timeout=60)
    if pal.returncode != 0:
        sys.exit(f"FAIL palace lookup: {pal.stderr.strip()[:200]}")
    pid = (json.loads(pal.stdout) or {}).get("_id")
    if not pid:
        sys.exit("FAIL no palace for client")
    print(f"  palaceId={pid}")

    # 1. embedding health must be configured (the credential is in the Convex env)
    h = subprocess.run(["npx", "convex", "run", "palace/queries:embeddingHealth", json.dumps({"palaceId": pid})],
                       cwd=MEMPALACE, env=_CRUN_ENV, capture_output=True, text=True, timeout=60)
    health = json.loads(h.stdout) if h.returncode == 0 and h.stdout.strip() else {}
    print(f"  embeddingHealth: configured={health.get('configured')} degraded={health.get('degraded')} counts={health.get('counts')}")
    if health.get("configured") is not True:
        sys.exit("FAIL embedder not configured in the Convex env. The ACTIVE provider is Bedrock Titan v2 "
                 "(set AWS_BEARER_TOKEN_BEDROCK via `convex env set`); the parked Gemini path uses GEMINI_API_KEY.")

    # 2. seed distinct docs (each embeds inline through ingestExchange → the configured embedder, Titan active)
    for tag, content in DOCS:
        w = broker.write(pid, SEAT, {"content": content, "title": f"proof-{tag}"})
        print(f"  write {tag}: status={w.get('status')}")
        if w.get("status") not in ("ok", "partial"):   # quarantined = NOT retrievable → not a clean proof
            sys.exit(f"FAIL write {tag} not stored retrievably: {w}")
    print(f"  seeded {len(DOCS)} docs as seat={SEAT}")

    # 3. semantic retrieve — the gate: ranked, non-empty, target on top (eventual-consistency retry)
    # Low floor so we can SEE scores (distinguish "no vectors" from "below the 0.35 broker floor").
    top = None
    for attempt in range(6):
        r = broker.retrieve(pid, SEAT, QUERY, k=5, similarity_floor=0.0)
        chunks = r.get("chunks") or []
        if chunks:
            print(f"  retrieve returned {len(chunks)} chunks; scores={[round(c.get('score') or 0, 3) for c in chunks]}")
            top = chunks[0]
            break
        print(f"  attempt {attempt}: 0 chunks (reason={r.get('reason')})")
        time.sleep(2)

    if not top:
        sys.exit("FAIL retrieve returned EMPTY — embedder dead or vectors absent (graceful-empty = failure here)")

    text = (top.get("text") or "")
    score = top.get("score")
    hit = TARGET_TOKEN.lower() in text.lower()
    print(f"  top score={score}  contains '{TARGET_TOKEN}'={hit}")
    print(f"  top text: {text[:120]!r}")
    if not hit:
        sys.exit(f"FAIL top hit is not the semantic target (expected '{TARGET_TOKEN}'): {text[:160]!r}")
    if not (isinstance(score, (int, float)) and score > 0):
        sys.exit(f"FAIL no real similarity score: {score!r}")

    print("== PASS — semantic retrieval works on the deployed stack (embedder live) ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
