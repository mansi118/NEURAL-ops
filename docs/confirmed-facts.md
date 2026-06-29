# Confirmed Facts (M0 · T0.3) — traced against live repo/Terraform/AWS, 2026-06-29

Per the execution plan's rule 4 (CONFIRM-TF: verify before acting; stop-and-flag on contradiction).
Account `071126865245`, `ap-south-1`. **Two plan assumptions (D1) contradict reality — flagged below.**

## Verified infrastructure facts
- **ECR repos:** `neos-dogfood-runtime` · `neos-dogfood-bridge` · `neos-dogfood-convex` · `neos-dogfood-falkordb` (all images pushed; spine live).
- **Dockerfiles:** runtime → `NEURAL-ops/Dockerfile`; bridge → `Mempalace_NEOS/services/Dockerfile`; convex + falkordb → mirrored from public images (ghcr/DockerHub → ECR).
- **Convex DB backend:** **SQLite-on-EFS**, `desired_count = 1` (single writer). NOT RDS. (Postgres-swap is the named multi-instance prerequisite.) → resolves T4.1: SQLite-on-EFS, no RDS for Convex.
- **Secrets Manager IDs:** `neos-dogfood/{ANTHROPIC_API_KEY, OPENROUTER_API_KEY, PALACE_BRIDGE_API_KEY, CONVEX_SELF_HOSTED_ADMIN_KEY, CONVEX_INSTANCE_SECRET, GEMINI_API_KEY, AWS_BEARER_TOKEN_BEDROCK}`. `OPENROUTER_API_KEY` is now a managed slot (M2 added it to `variables.tf`; set the value out-of-band). `EMBEDDER_API_KEY` was dropped (T1.5 — vestigial; embeddings are server-side in Convex).
- **Runtime LLM env var:** `CLASSIFIER_PROVIDER` selects the provider; `PROVIDER_KEYS = {anthropic: ANTHROPIC_API_KEY, openrouter: OPENROUTER_API_KEY}`. **D2 DECIDED + SHIPPED (M2, #46): `llm_provider`/`CLASSIFIER_PROVIDER` default = `openrouter`**; classifier id = `anthropic/claude-haiku-4.5` (the `-3.5-haiku` slug 404s). See `docs/decisions/ADR-llm.md`.
- **Network:** `enable_nat_gateway = false` (deployed). VPC endpoints only: ecr.api/dkr · s3 · logs · secretsmanager · **bedrock-runtime**. ⇒ the deployed Convex has **no internet egress**; only AWS services via PrivateLink are reachable.
- **Live embedder TODAY:** `lib/embedder.ts` selector → `qwen.js` = **Bedrock Titan v2 @ 1024-dim** via the bedrock-runtime PrivateLink endpoint. Live-proven (ranked retrieval). `lib/gemini.ts` exists but parked (gemini-embedding-001 @ 1024 via MRL). Schema vector index = **1024-dim**.

## ⚠ CONTRADICTION C1 — D1's "native Gemini embedding-001 @ 768" is NOT available on this key
Tested `embedContent` live (2026-06-29):
- `models/embedding-001` → **404** (not found for v1beta).
- `models/text-embedding-004` → **404**.
- `models/gemini-embedding-001` → **OK, 3072-dim native**. 768 is reachable ONLY via `outputDimensionality` (MRL truncation) — the mechanism D1 explicitly says to *supersede*.
**⇒ D1's premise is false:** there is no native-768 Gemini model on this key. The only 768 path is MRL-768
(which D1 disavowed believing native-768 existed). **Decision needed** — see below.

## ⚠ CONTRADICTION C2 — Gemini cannot run on the deployed (no-NAT) Convex
Gemini's API is external internet with **no AWS VPC endpoint**. The deployed Convex is `enable_nat_gateway=false`
(no egress). So **any** Gemini variant (768 or 3072) is **unreachable from the live spine** until a NAT gateway
is added (needs an Elastic IP — the account's EIP quota was the original wall). Bedrock Titan works precisely
because it has a PrivateLink endpoint. The plan adds NAT only at **Phase 3 (M6)**, but **M4 (Phase 2)** requires
the embedder live for "real ranked retrieval" — a sequencing conflict.

## Achievable embedder options (pick one — this is the M1 decision)
| Option | Provider / dim | Works on live no-NAT spine? | Honors D1? |
|---|---|---|---|
| **A (status quo)** | Bedrock Titan **@1024**, PrivateLink | ✅ yes (live-proven) | ✗ not Gemini, not 768 |
| **B** | Gemini-embedding-001 **MRL-768** + L2-norm + asymmetric task types | ❌ needs NAT (EIP) | ~ Gemini+768+asymmetric, but via MRL (D1 disavowed MRL) |
| **C** | Gemini native **3072** | ❌ needs NAT (EIP) | ~ Gemini+asymmetric, 4× index cost, not 768 |
**DECIDED (2026-06-29): ship Option A (Titan @1024) for V1.** It works on the live no-NAT spine and the
ranked-retrieval done-bar is met (not "calls succeed"). **Option B (Gemini MRL-768) is parked/optional**,
not a blocker — promote it only if a reason bites: spec-alignment (S2 §2.5.3), portability (Titan ties V1 to
this account's Bedrock model-access state + a service-specific credential), or cost. Promotion is gated on
the **NAT decision** (Gemini needs egress) and is a free re-index pre-onboarding (one-line selector flip,
PR #26 held open). Full decision record + lock-in detail: `docs/decisions/embedder-as-built.md`.

## Other deltas
- **T0.1/D2 (runtime LLM) — ✅ DECIDED + SHIPPED (M2, #46): OpenRouter primary** (`docs/decisions/ADR-llm.md`).
- T0.2/G-b (cred rotation) — **parked per ML instruction ("leave the credentials thing")**; not pursued.
- **Embedder — ✅ as-built = Titan @1024 (#41 + #25 merged); Gemini-768 (#26) parked** (`embedder-as-built.md`).
