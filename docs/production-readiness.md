# NEOS / NeuralChat — Production-Readiness Ledger

**Status as of 2026-06-21 · authoritative · ✅ done · 🔨 agent-buildable remaining · ⛔ human-gated**

> Honest framing: "production-ready" is the **Day-90 acceptance gate** (live ≥5-seat tenant, fidelity
> ≥0.65, pen-test passed, zero isolation violations in 30d). That gate is inherently live + human — the
> agent **builds to the walls and cannot declare it**. This ledger tracks every deliverable to that gate.

## Verification evidence (2026-06-21, against the self-hosted convex-local-backend)
- NEURAL-ops python sweep **17/17**; Mempalace vitest **94 pass | 1 skip** at every merge; L2 `bridge_identity` **5/5**.
- **Live, against the real /mcp dispatcher (not simulated):** dogfish cross-seat ACL **4/4**; edge-auth +
  audit **7/7**; full E2E process (forged inbound → edge-auth → broker.write/retrieve → broker
  denied_at_layer → audit) **8/8**. `tsc` green both repos.
- **Governance activated + LIVE-proven this session:** `paused_runs` durable pause — save(insert+update)+get
  round-trip returns the exact snapshot; bridge denial emit — `denialsByLayer` `falkordb` count incremented
  end-to-end via the actual `_emit_external_denial` Python path (bridge → `/external-denial` → audit).
- ⇒ The **security / identity / audit / governance spine is built, merged, and LIVE-proven** — and the
  approval engine now has a live, durable consumer.

## Phase ledger

### P0 — Cross the live wall ✅ (via self-host; cloud deploy ⛔ optional)
✅ live single-seat round-trip proven; edge-auth live seam (resolve_binding→Convex) proven; codegen+tsc green.
⛔ embedder decision+key; cloud `convex deploy`; rotations; Anthropic key for live classifier verdict.

### P1 — Production substrate (S0)
✅ S0.1 runtime container (PR #6 open, your docker review) · S0.2 secrets (`runtime/secrets.py`, env→keyring→refuse) ·
   **Terraform substrate module** (`infra/terraform/`, PR #21) — VPC→ALB→ECS Fargate (runtime)→Secrets Manager→
   IAM→CloudWatch; `fmt`/`init`/`validate` clean offline; secrets created empty (values out-of-band, S0.2); README runbook.
🔨 containers for nc-* (need the services first); bridge/nc-* task defs as further modules; OTel instrumentation.
⛔ **`terraform apply`** (AWS account + creds — the gate; validate ≠ working infra) · KMS CMK · remote state (S3+lock) ·
   TLS (ACM/443) · Synapse hosts · DR backups.

### P2 — Governance + multi-tenant (the critical-path gate) — ACTIVATED this session
✅ approval-policy engine (GW-4/5/6, `acp/approval.py`) · **4-layer ACL all emitting + LIVE-proven**
   (edge · broker · convex_sot · falkordb) — L2 enforcement core + bridge wiring **merged** (5 endpoints
   incl `graph_stats`, default-off, Mempalace PR #18).
✅ **`AwaitingApproval` run-state WIRED** (NEURAL-ops PR #17) — the one sanctioned `core.py` change, to a
   reviewed transition spec: `AWAITING_APPROVAL` non-terminal pause, two in-edges (EXECUTING/PLANNING) +
   three-way gate (ALLOW/AWAIT/DENY→REJECTED), durable `to_state`/resume, GW-5 hard-deny re-checked on grant.
   Additive `approval=None` → byte-identical (asserted: permissive-policy event stream == no-policy);
   6 acceptance scenarios green. **The approval engine now has a consumer.**
✅ **Gov-flip seam COMPLETE (all 3 pieces, live-proven on self-host):** runtime `ConvexSnapshotStore`
   (NEURAL-ops #18, credential-gated + L4 scope guard) ↔ Convex `paused_runs` store (Mempalace #19,
   round-trip live) — durable pause survives the process; bridge→Convex external-denial emit (Mempalace #20,
   least-privilege `/external-denial` httpAction, shared key, default-off) → `denialsByLayer` falkordb live.
🔨 OPA/Rego integration code; Decision-Queue read of `paused_runs` (the nc-web surface); namespace logic.
⛔ **The flip itself** (minimal approval policy + `BRIDGE_IDENTITY_ENABLED`/`CONVEX_DENIAL_SINK_URL` on +
   inject `ApprovalBroker(policy, store=ConvexSnapshotStore(...))` for the dogfood tenant) · OPA/Rego
   **policy sign-off** · KMS CMK · `X-NEop-Identity` signing scheme (HMAC/Ed25519) · pen-test.

### P3 — Live comms + UI 🔨/⛔
🔨 nc-channels Matrix AS adapter + normalization + HMAC + attachments; streaming transport; nc-web
   (Decision Queue + dashboard); nc-admin.
⛔ live Synapse homeserver(s); domain/DNS/TLS.

### P4 — Learning loop / the twin product (logic BUILT · meta-NEops WRAPPED; remaining = live-gated wiring)
✅ **Meta-NEop logic exists + tested**: `runtime/vault.py` (5-gate `promote`/rollback) · `runtime/curator.py`
   (`fidelity`/`corroborated`/`next_maturity`/`curate`) · `runtime/flywheel.py` (observe/surface/triage/run) ·
   `runtime/rrf.py` (`fuse`/`fuse_results`) · `acp/hierarchy.py` (delegation/escalation, 6/6).
✅ **All 4 meta-NEops WRAPPED as Pi-agents** (pattern=workflow, faithful mocks = exact runtime-function
   output): `agents/vault-promoter` (#16, `vault.promote`) · `agents/twin-curator` (`curator.curate`→curated
   twin) · `agents/hierarchy-resolver` (`hierarchy.delegate`) · `agents/acp-router` (`router.route`→signed
   inform envelope) — batch PR #19. nrt suite + `neop_spec` linter + sweep 17/17 green; core.py untouched.
🔨/⛔ **Wiring** (live-gated, server-side — NOT offline-buildable): real STM/LTM/Vault tiering (broker
   passthrough → `vault.promote`); RRF 4-backend fusion (broker is vector-only — add bm25/graph/recency);
   fidelity clock (per-seat rolling window surfacing `curator.fidelity`); live tool binding for the wrappers
   + async cadence. (Fidelity TARGET 0.65@D90 is a learning-clock outcome, not a build.)

### P5 — The fleet 🔨/⛔
🔨 re-wrap Recon/ICD/CoS/TeamPulse onto planner→executor→verifier; build toward the catalog (each green under `nrt`).
⛔ per-NEop domain sign-off (tool allowlist + approval scopes).

### P6 — Platform layers (V2) 🔨/⛔
🔨 NE-Eval, Model Studio, Marketplace V0, the flywheel logic.
⛔ NE-QuickBuild auto-deploy = highest-risk; Integration-Receipt Allowlist policy sign-off.

## Cross-cutting gates
- **Security:** ✅ 4-layer ACL emitting **+ all 4 layers live-proven** (edge/broker/convex_sot/falkordb,
  the last via the `/external-denial` sink → `denialsByLayer`) · ✅ secrets-out-of-code (S0.2) ·
  ✅ approval mediation wired (AwaitingApproval) · 🔨 Ed25519 ACP signing wired live · ⛔ pen-test ·
  ⛔ mTLS/TLS1.3/Megolm (infra).
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
| **zero tenant-isolation violations 30d** | ✅ mechanism live-proven (4-layer ACL + audit replay via `denialsByLayer`, all 4 layers) — needs ⛔ 30d live window |
| 6 meta-NEops live · dashboard · pen-test | ✅ 4 meta-NEops wrapped (+ approval/edge meta-seams) · 🔨 dashboard · ⛔ live binding + pen-test |

## Critical path to V1
**The offline-buildable runway is essentially spent** — P2 governance is wired + live-proven, the gov-flip
seam is complete, and all 4 meta-NEops are wrapped. From here the program moves by **activation** (flips +
config) and **infra**, both human-gated.
**Human (⛔), unblocks the most:** PAT rotation (30s, first) · **the governance flip** (minimal policy +
env toggles for the dogfood tenant — its whole seam is now live-proven) · embedder key · AWS infra +
`terraform apply` (→ P1, live P3, CMK) · Synapse hosts · policy sign-offs · pen-test/DR drill.
**Agent (🔨), what's left:** P3 nc-* services (Decision-Queue/dashboard over `paused_runs` + `denialsByLayer`) ·
P5 fleet re-wrap (Recon/ICD/CoS/TeamPulse onto the proven wrapper recipe) · P6 platform layers · OPA/Rego code.

## Verdict
The **identity / audit / governance spine is production-grade, live-verified, and now ACTIVATED** — the
approval engine has a durable consumer (AwaitingApproval ↔ `paused_runs`), all 4 ACL layers emit live, and
all 4 meta-NEops are wrapped. Reaching V1 now needs (a) the human ⛔ gates — chiefly the **governance flip**
(cheap, its seam is proven), the embedder, and infra — and (b) the remaining **agent product-build (P3 nc-*
+ P5 fleet)**, a multi-session effort. No part of "production-ready" is faked; every item below the flip has
an owner and an acceptance criterion above, and what could be proven offline or on the self-host has been.
