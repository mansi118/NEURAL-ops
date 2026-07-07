# Box proofs A & B — the "it's alive" card (model generates · memory ranks)

> **Confidentiality:** INTERNAL — NeuralEDGE / Synlex.
> **What this is.** A copy-paste pass/fail card for the two proofs that make a NEop *think with memory*:
> **Proof A** — the model RESOLVES and GENERATES in-VPC; **Proof B** — memory RANKS a seeded query.
> They are the model-and-memory core of Phase 1 in `bar2-first-live-turn-runbook.md` (this card makes 1A + the
> in-VPC-generate half concrete; A2/GAP-2/T9 stay in that runbook). **These are different proofs** — A is
> "generates", B is "ranks" — run BOTH; neither implies the other. Every green means EXACTLY what it says.
> **Prerequisite (`[U]`):** the `ap-south-1`-scoped `AWS_BEARER_TOKEN_BEDROCK` is minted and provisioned. A
> us-east-1 token 403s in-spine. Both proofs run **in-VPC** (CodeBuild `neos-dogfood-spine-verify` /
> `infra/build/spine-verify.sh`) — the no-NAT spine reaches Bedrock + palace via PrivateLink only.

---

## Proof A — Nova generates in-VPC  (`resolves ≠ generates`)
**Tool:** `nrt probe-model` (pi-neop-runtime; `pi-neop-runtime#8`). A bare, tool-less single generation —
deliberately NOT the classifier (that conflates the model layer with routing).

**Run (in-VPC, in the seat env):**
```
NEOP_PROVIDER=amazon-bedrock \
AWS_BEARER_TOKEN_BEDROCK=<ap-south-1 bearer> \
nrt probe-model
# NRT_MODEL defaults to apac.amazon.nova-lite-v1:0; the broker pins AWS_REGION=ap-south-1
```

**PASS / FAIL:**
| Result | Meaning |
|---|---|
| `ok resolved model id = apac.amazon.nova-lite-v1:0` then `PASS` / `PASS*` | **GREEN** — model resolves AND returns a non-empty completion in-VPC. (`PASS*` = generated but didn't echo the sentinel: generation works, eyeball the printed text for coherence.) |
| `FAIL resolution — …` | broker didn't construct — blank/again-check the bearer env (fail-closed before any call). |
| `FAIL generate — AUTH/REGION (403)` | bearer invalid or **wrong region** (us-east-1 token in ap-south-1). |
| `FAIL generate — MODEL-NOT-GRANTED` | account can't invoke this id — confirm the `apac.*` profile (bare `amazon.nova-*` rejects on-demand). |
| `FAIL generate — EGRESS/DNS` | can't reach `bedrock-runtime.ap-south-1.amazonaws.com` — the **GAP-2 jail allowlist (#97)** must permit it AND PrivateLink private-DNS must resolve it. *host-in-map ≠ connection-succeeds.* |

**A green here is triple-duty:** it proves the model path (#8) live, AND — since the same bearer/PrivateLink
path serves Convex ingestion extraction — that the **write-quarantine fix is live** (aria's never-persisting
was extraction's model call failing from no-NAT). Confirm the deployed Convex has the same `ap-south-1` bearer.

---

## Proof B — memory ranks a seeded query  (`retrieval ran ≠ ranked memory came back`)
**Tool:** `tools/ranked_retrieval_proof.py` (already the GAP-1 acceptance shape; **graceful-empty = HARD FAIL**).

**Run (in-VPC):**
```
NEOS_SMOKE_API_URL=<convex .cloud>  NEOS_SMOKE_SITE_URL=<convex .site>  \
NEOS_SMOKE_ADMIN_KEY=<admin>  MEMPALACE_DIR=<path>  \
python3 tools/ranked_retrieval_proof.py
```
Seeds a disposable, obviously-synthetic canary (`CANARY-NEUOPS-7Z3Q`, seat `zzz-ranked-canary-smoke`) then
queries it two ways:
- **NEAR** (`"what is the fallback passphrase?"`) — high lexical overlap (easy).
- **OBLIQUE** (`"where does the team regroup after an outage?"`) — low-overlap, semantic (the #30 case).

**PASS / FAIL (the bar is literal):**
| Check | GREEN requires |
|---|---|
| **Persistence** | the canary comes back at all (not-indexed-yet/empty ⇒ **write-quarantine finding**, priority — and points back at Proof A's extraction path). |
| **NON-EMPTY** | `len(chunks) > 0` on both queries — **graceful-empty = HARD FAIL**, held literally. |
| **rank-1 == canary** | the canary is the **top** hit on BOTH near AND oblique (mis-rank on oblique ⇒ **#30 ranking gap**). |
| **ABS_MIN** | pin `ABS_MIN` **below the OBLIQUE landing score** the run prints — not the near hit. |

**Green = MEMORY RANKS.** This is the moment a NEop can think with real memory.

**Honest scope (name it):** this tool proves the **palace/embedder ranks** (via the Python `runtime.memory`
broker — the shared substrate). Hermes's `palaceClient.ts` calling `palace_search` correctly is **unit-proven**
(16 tests, scope-baked/fail-closed). So B1 = *palace-ranks (this proof)* ∧ *palaceClient-contract (units)*.

### Proof B2 — Hermes composition  (`palace ranks ≠ Hermes retrieves`)
**Tool:** `nrt probe-memory` (pi-neop-runtime; `#8`) — the memory-side twin of `probe-model`. Retrieves the
**same oblique canary** end-to-end through pi-neop-runtime's own `MemoryBroker`/`palaceClient`, so the Hermes
composition is *proven*, not inferred.
```
PALACE_MCP_URL=<…/mcp>  PALACE_ID=<tenant>  NEOP_ID=<the permissioned canary seat>  nrt probe-memory
# defaults the query to the oblique canary "where does the team regroup after an outage?"
```
| Result | Meaning |
|---|---|
| `PASS  Proof B (composition) — Hermes RETRIEVES…` + a rank-1 chunk | **GREEN** — the composition works; eyeball rank-1 for the canary. |
| `FAIL retrieval returned []` | graceful-empty = HARD FAIL. **Cross-check B1:** B1 green + this empty ⇒ the **Hermes composition** is the fault; both empty ⇒ the palace/write path. |
| `FAIL retrieve — ACL-DENIED (403)` | the seat isn't permissioned — the **seed:access** ML gate, not a wiring bug. |
| `FAIL … SCOPE / EGRESS-DNS / PALACE-ERROR` | scope blank/reserved · can't reach `/mcp` · Convex 5xx — each named + attributable. |

**Sequencing (non-blocking):** run **B1 in the box-verify NOW** (it's the highest-information read, gated only
on the bearer mint). **B2 (`probe-memory`) is a strengthening, not a prerequisite** — land it so the memory
composition is proven *before T9*, not before the box-verify. Its standing value: if a live turn later has a
memory failure, B2 is the instrument that says *palace (B1-green) vs Hermes-path* — the attribution you'd
otherwise lack. **Green = MEMORY RANKS end-to-end through Hermes.**

---

## After both green
Proof A + Proof B green = **the model thinks and the memory ranks, in-VPC.** That is the substance of "it's
alive" — but it is **not yet a live turn**: A2 (injection-resistance vs the live model), GAP-2 enforcement
(the jail actually dropping a third host), the Bar-1a transport echo, then **T9 (STOP-AND-ASK)** remain, per
`bar2-first-live-turn-runbook.md`. Run these two first — they isolate the model+memory core, so a later
live-turn failure is definitely the seam, not the brains.
