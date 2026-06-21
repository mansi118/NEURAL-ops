# NEOS / NeuralChat — Production-Readiness Ledger

**Status as of 2026-06-21 · authoritative · ✅ done · 🔨 agent-buildable remaining · ⛔ human-gated**

> Honest framing: "production-ready" is the **Day-90 acceptance gate** (live ≥5-seat tenant, fidelity
> ≥0.65, pen-test passed, zero isolation violations in 30d). That gate is inherently live + human — the
> agent **builds to the walls and cannot declare it**. This ledger tracks every deliverable to that gate.

## Verification evidence (2026-06-21, against the self-hosted convex-local-backend)
- NEURAL-ops python sweep **15/15**; Mempalace vitest green at every merge; L2 `bridge_identity` **5/5**.
- **Live, against the real /mcp dispatcher (not simulated):** dogfish cross-seat ACL **4/4**; edge-auth +
  audit **7/7**; full E2E process (forged inbound → edge-auth → broker.write/retrieve → broker
  denied_at_layer → audit) **8/8**. `tsc` green both repos.
- ⇒ The **security / identity / audit spine is built, merged, and LIVE-proven.**

## Phase ledger

### P0 — Cross the live wall ✅ (via self-host; cloud deploy ⛔ optional)
✅ live single-seat round-trip proven; edge-auth live seam (resolve_binding→Convex) proven; codegen+tsc green.
⛔ embedder decision+key; cloud `convex deploy`; rotations; Anthropic key for live classifier verdict.

### P1 — Production substrate (S0)
✅ S0.1 runtime container (PR #6 open, your docker review) · S0.2 secrets (`runtime/secrets.py`, env→keyring→refuse).
🔨 containers for nc-* (need the services first); Terraform tenant-provisioning **module** (validate offline);
   OTel instrumentation (needs services).
⛔ ECS/EC2/ALB/VPC, Secrets Manager, KMS, S3, Synapse hosts; the `terraform apply`; DR backups.

### P2 — Governance + multi-tenant (the critical-path gate)
✅ approval-policy engine (GW-4/5/6, `acp/approval.py`) · **4-layer ACL all emitting** (edge · broker ·
   convex_sot · falkordb) — FalkorDB L2 enforcement core + bridge wiring (5 endpoints, default-off flag).
🔨 **`AwaitingApproval` run-state** — the ONE sanctioned `core.py` change (surface design first); OPA/Rego
   integration code; bridge→Convex live `recordExternalDenial` emit; namespace logic.
⛔ OPA/Rego **policy sign-off**; KMS CMK; `X-NEop-Identity` signing scheme (HMAC/Ed25519); pen-test.

### P3 — Live comms + UI 🔨/⛔
🔨 nc-channels Matrix AS adapter + normalization + HMAC + attachments; streaming transport; nc-web
   (Decision Queue + dashboard); nc-admin.
⛔ live Synapse homeserver(s); domain/DNS/TLS.

### P4 — Learning loop / the twin product 🔨 (all agent-buildable on the proven substrate — NEXT)
🔨 memory tiering real (STM/LTM/Vault, replace passthrough); RRF 4-backend fusion; the **4 remaining
   meta-NEops** (Vault Promoter · Twin Curator · Hierarchy Resolver · ACP Router); fidelity clock + twin
   maturity machine. (Fidelity TARGETS 0.65@D90 are a learning-clock outcome, not a build.)

### P5 — The fleet 🔨/⛔
🔨 re-wrap Recon/ICD/CoS/TeamPulse onto planner→executor→verifier; build toward the catalog (each green under `nrt`).
⛔ per-NEop domain sign-off (tool allowlist + approval scopes).

### P6 — Platform layers (V2) 🔨/⛔
🔨 NE-Eval, Model Studio, Marketplace V0, the flywheel logic.
⛔ NE-QuickBuild auto-deploy = highest-risk; Integration-Receipt Allowlist policy sign-off.

## Cross-cutting gates
- **Security:** ✅ 4-layer ACL emitting · ✅ secrets-out-of-code (S0.2) · 🔨 Ed25519 ACP signing wired live ·
  ⛔ pen-test · ⛔ mTLS/TLS1.3/Megolm (infra).
- **Reliability (SLOs):** chat p95 ≤2s / NEop run p95 ≤60s / retrieval p95 ≤1.2s — measurable only on the
  deployed stack (⛔). DR drill ⛔.
- **Compliance:** DPDP/residency/SOC2/ISO — ⛔ (org + infra).

## V1 Day-90 acceptance scorecard
| Criterion | Status |
|---|---|
| ≥5 seats onboarded, twin.md v≥5 | ⛔ live tenant |
| ≥3 NEops/seat in regular use | 🔨 P5 re-wrap, then ⛔ usage |
| twin fidelity ≥0.65 | 🔨 P4 fidelity clock, then ⛔ usage outcome |
| chat p95 ≤2s / NEop run p95 ≤60s | ⛔ deployed-stack measurement |
| **zero tenant-isolation violations 30d** | ✅ mechanism live-proven (4-layer ACL + audit replay via `denialsByLayer`) — needs ⛔ 30d live window |
| 6 meta-NEops live · dashboard · pen-test | 🔨 (4 meta-NEops + dashboard) + ⛔ pen-test |

## Critical path to V1
**Human (⛔), unblocks the most:** AWS infra + `terraform apply` (→ P1, live P3, CMK) · embedder key ·
Synapse hosts · rotations · policy sign-offs · pen-test/DR drill.
**Agent (🔨), in order:** finish P2 (`AwaitingApproval` after design surface; bridge live emit) → **P4
learning loop** (memory tiering + RRF + 4 meta-NEops + fidelity clock) → P5 fleet re-wrap → P6.

## Verdict
The **identity / audit / governance spine is production-grade and live-verified.** Reaching V1 needs:
(a) the human ⛔ gates (infra, embedder, sign-offs, pen-test, the live tenant), and (b) the remaining
**agent product-build (P4→P5)** — a multi-session effort, not one turn. No part of "production-ready" is
faked; each remaining item has an owner and an acceptance criterion above.
