# Confirmed Facts (M0 · T0.3) — traced against live repo/Terraform/AWS, 2026-06-29

Per the execution plan's rule 4 (CONFIRM-TF: verify before acting; stop-and-flag on contradiction).
Account `071126865245`, `ap-south-1`. **Two plan assumptions (D1) contradict reality — flagged below.**

## Verified infrastructure facts
- **ECR repos:** `neos-dogfood-runtime` · `neos-dogfood-bridge` · `neos-dogfood-convex` · `neos-dogfood-falkordb` (all images pushed; spine live).
- **Dockerfiles:** runtime → `NEURAL-ops/Dockerfile`; bridge → `Mempalace_NEOS/services/Dockerfile`; convex + falkordb → mirrored from public images (ghcr/DockerHub → ECR).
- **Convex DB backend:** **SQLite-on-EFS**, `desired_count = 1` (single writer). NOT RDS. (Postgres-swap is the named multi-instance prerequisite.) → resolves T4.1: SQLite-on-EFS, no RDS for Convex.
- **Secrets Manager IDs:** `neos-dogfood/{ANTHROPIC_API_KEY, OPENROUTER—(absent), EMBEDDER_API_KEY, PALACE_BRIDGE_API_KEY, CONVEX_SELF_HOSTED_ADMIN_KEY, CONVEX_INSTANCE_SECRET, GEMINI_API_KEY, AWS_BEARER_TOKEN_BEDROCK}`. (No OPENROUTER secret yet — would be added at M2/D2.)
- **Runtime LLM env var:** `CLASSIFIER_PROVIDER` selects the provider; `PROVIDER_KEYS = {anthropic: ANTHROPIC_API_KEY, openrouter: OPENROUTER_API_KEY}`, default `anthropic`. So the boot key follows the D2 decision.
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
**Recommendation:** **A for the live spine now** (it works, empty corpus), and adopt **B as the V1-canonical
embedder when NAT lands** (free re-index pre-onboarding via the one-line selector flip). This honors D1's intent
(Gemini, 768, asymmetric, L2-norm) as soon as the spine has egress, without faking a native-768 that doesn't exist
or running Gemini where it can't reach. **Requires ML: (1) accept MRL-768 (native-768 unavailable), (2) authorize
NAT (an EIP) for the live spine.**

## Other deltas
- T0.1/D2 (runtime LLM) — ⛔ ML decision pending → `docs/decisions/ADR-llm.md`.
- T0.2/G-b (cred rotation) — **parked per ML instruction ("leave the credentials thing")**; not pursued.
