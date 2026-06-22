# NEOS / NeuralChat — Production-Readiness Ledger

**Status as of 2026-06-22 · authoritative · ✅ done · 🔨 agent-buildable remaining · ⛔ human-gated**

> Honest framing: "production-ready" is the **Day-90 acceptance gate** (live ≥5-seat tenant, fidelity
> ≥0.65, pen-test passed, zero isolation violations in 30d). That gate is inherently live + human — the
> agent **builds to the walls and cannot declare it**. This ledger tracks every deliverable to that gate.
>
> **2026-06-22 — BUILT TO THE WALL.** Every agent-buildable surface on the deploy path is merged to `main`
> (seven PRs this stretch: #30 #34 #35 #36 #37 #38 + #6). Nothing `[A]` remains to *reach* a deploy — the
> rest is the `[U]` path (PAT → AWS → `terraform apply` → secrets → deploy → smoke → flip → Day-90). The
> remaining 🔨 are product surfaces (nc-web UI/channels app, P5 fleet) NOT on the first-live-run critical path.

## Verification evidence (2026-06-22, against the self-hosted convex-local-backend)
- NEURAL-ops python sweep **20/20**; Mempalace vitest **95 pass | 1 skip** at every merge; L2 `bridge_identity` **5/5**.
- **Live, against the real /mcp dispatcher (not simulated):** dogfish cross-seat ACL **4/4**; edge-auth +
  audit **7/7**; full E2E (forged inbound → edge-auth → broker.write/retrieve → denied_at_layer → audit) **8/8**.
  `tsc` green both repos; the parameterized **deployed-stack smoke 7/7** (ready to point at AWS).
- **Governance activated + LIVE-proven:** `paused_runs` durable pause round-trips the exact snapshot; the
  **Decision Queue** loop (`pendingPausedRuns` save→count 1→resolve→count 0); and **all 4 ACL layers now emit**
  to the unified audit from production code — `denialsByLayer` = convex_sot 6 / falkordb 2 / **broker 1** /
  **edge 2** (each driven by the real runtime/bridge/edge-auth path, not a smoke).
- **Twin = identity, per-user — LIVE-proven:** a **permission-less** seat reads+writes its **own** twin while
  the **same seat is still denied a memory op** (`palace_search`) — the B2 carve-out is exactly twin-specific.
- **Edge emit timing-safe (verify-by-absence):** the edge audit emit runs off the rejection's critical path
  (`_dispatch`), so a rejection's latency does not vary with palace resolution — no tenant-existence oracle.
- ⇒ The **security / identity / audit / governance spine is built, merged, and LIVE-proven**, the approval
  engine has a live durable consumer, and the **full AWS substrate is expressed in Terraform (validate-clean)**.

## Phase ledger

### P0 — Cross the live wall ✅ (via self-host; cloud deploy ⛔ optional)
✅ live single-seat round-trip proven; edge-auth live seam (resolve_binding→Convex) proven; codegen+tsc green.
⛔ embedder decision+key; cloud `convex deploy`; rotations; Anthropic key for live classifier verdict.

### P1 — Production substrate (S0) — FULL TERRAFORM SUBSTRATE on main, validate-clean
✅ S0.1 runtime container (PR #6 **merged**) · S0.2 secrets (`runtime/secrets.py`, env→keyring→refuse).
✅ **Terraform substrate — complete + validate-clean** (`infra/terraform/`): VPC/subnets/NAT · ALB (+TLS gated:
   ACM/443/redirect, #32) · ECS Fargate **runtime** (#21) · **bridge + FalkorDB sidecar + EFS** (#31) · **ECR +
   KMS CMK + KMS-encrypted secrets/logs** (#31) · **self-host Convex on ECS + EFS** (the SoT, #36) · **comms tier:
   ElastiCache Redis + NATS + ClickHouse + Synapse(+RDS Postgres)** (#37) · Cloud Map internal DNS · Bedrock IAM
   (gated). Secrets created empty (values out-of-band, S0.2). `fmt`/`init`/`validate` clean; README apply-runbook.
✅ Deployed-stack smoke (`tools/deployed_stack_smoke.py`, #38) — target-agnostic spine verification, 7/7 vs self-host.
🔨 OTel instrumentation; nc-* service containers (need the service code — P3).
⛔ **`terraform apply`** (AWS account + creds — the gate; validate ≠ working infra) · remote state (S3+lock) · DR backups.
   Named substrate forward-deps (managed, not hidden): **single-writer Convex** (SQLite-on-EFS, `desired_count=1` —
   a Postgres-backend SWAP is a prerequisite for multi-instance, not a tuning knob) · Redis HA (replica+failover) ·
   NATS JetStream durability (EFS) · Synapse PUBLIC client-API ingress (ALB host rule + federation) · RDS multi-AZ.

### P2 — Governance + multi-tenant (the critical-path gate) — ACTIVATED this session
✅ approval-policy engine (GW-4/5/6, `acp/approval.py`) · **4-layer ACL enforcing; 3/4 layers EMIT to the
   unified audit from production code + LIVE-proven** — `convex_sot` (native), `falkordb` (bridge
   `_emit_external_denial`, Mempalace PR #20), `broker` (runtime `audit_emit`, PR #27 — live: broker
   denial → `denialsByLayer.broker` 0→1). L2 enforcement core + bridge wiring merged (5 endpoints incl
   `graph_stats`, Mempalace PR #18). **EDGE layer: classifies (`denied_at_layer=edge`) but does NOT yet
   emit** — `resolve_edge_identity` fails before resolving tenant-name→palaceId, so it has no key; needs a
   name→palaceId resolver at the edge seam (🔨, named below — NOT faked).
✅ **`AwaitingApproval` run-state WIRED** (NEURAL-ops PR #17) — the one sanctioned `core.py` change, to a
   reviewed transition spec: `AWAITING_APPROVAL` non-terminal pause, two in-edges (EXECUTING/PLANNING) +
   three-way gate (ALLOW/AWAIT/DENY→REJECTED), durable `to_state`/resume, GW-5 hard-deny re-checked on grant.
   Additive `approval=None` → byte-identical (asserted: permissive-policy event stream == no-policy);
   6 acceptance scenarios green. **The approval engine now has a consumer.**
✅ **Gov-flip seam COMPLETE (all 3 pieces, live-proven on self-host):** runtime `ConvexSnapshotStore`
   (NEURAL-ops #18, credential-gated + L4 scope guard) ↔ Convex `paused_runs` store (Mempalace #19,
   round-trip live) — durable pause survives the process; bridge→Convex external-denial emit (Mempalace #20,
   least-privilege `/external-denial` httpAction, shared key, default-off) → `denialsByLayer` falkordb live.
✅ **Twin keyed per-USER, not per-NEop** (reviewed-spec → wire, `docs/decisions/twin-keying.md`): `core.py`
   `twin_owner = msg.get("requester") or seat` (NEURAL-ops #23, backward-compatible — no requester ⇒
   byte-identical) + **B2 carve-out** (Mempalace #21) — the twin is **identity, not memory**: `palace_get_twin`/
   `palace_put_twin` ungated from recall/remember via `identityOnlyPerms`, own-twin = exact server-derived
   `neopId`. Working memory stays per-seat. Security linchpin: `requester` is server-derived (edge-auth E1–E5,
   unforgeable). `test_twin_keying.py` 4/4 incl. *two distinct NEops + same requester share ONE twin*.
⛔ **The flip itself** (minimal approval policy + `BRIDGE_IDENTITY_ENABLED`/`CONVEX_DENIAL_SINK_URL` on +
   inject `ApprovalBroker(policy, store=ConvexSnapshotStore(...))` for the dogfood tenant) · OPA/Rego
   **policy sign-off** · KMS CMK · `X-NEop-Identity` signing scheme (HMAC/Ed25519) · pen-test.
   **Named forward-dependency (Gate D / S0.3):** twin-keying is broker-trusted today (broker sets `requester`
   from the verified identity); when signed-identity lands, twin ops must derive the **requester** server-side
   (memory ops keep deriving seat) — pinned in `docs/decisions/twin-keying.md`, not hidden.

### P3 — Live comms + UI 🔨/⛔
✅ **Decision Queue read API + resume-resolve loop** — `pendingPausedRuns` (lists pending pauses, surfaces
   the gated action) + `markPausedRun` + runtime resolve-on-resume (Mempalace #22, NEURAL-ops #26);
   live-proven (save→queue count 1→resolve→0). The human-in-the-loop backend AwaitingApproval serves.
🔨 nc-channels Matrix AS adapter + normalization + HMAC + attachments; streaming transport; nc-web
   **UI** over the Decision Queue API + dashboard over `denialsByLayer`; nc-admin.
⛔ live Synapse homeserver(s); domain/DNS/TLS.

### P4 — Learning loop / the twin product (logic BUILT · meta-NEops WRAPPED; remaining = live-gated wiring)
✅ **Meta-NEop logic exists + tested**: `runtime/vault.py` (5-gate `promote`/rollback) · `runtime/curator.py`
   (`fidelity`/`corroborated`/`next_maturity`/`curate`) · `runtime/flywheel.py` (observe/surface/triage/run) ·
   `runtime/rrf.py` (`fuse`/`fuse_results`) · `acp/hierarchy.py` (delegation/escalation, 6/6).
✅ **All 4 meta-NEops WRAPPED as Pi-agents** (pattern=workflow, faithful mocks = exact runtime-function
   output): `agents/vault-promoter` (#16, `vault.promote`) · `agents/twin-curator` (`curator.curate`→curated
   twin) · `agents/hierarchy-resolver` (`hierarchy.delegate`) · `agents/acp-router` (`router.route`→signed
   inform envelope) — batch PR #19. nrt suite + `neop_spec` linter + sweep 17/17 green; core.py untouched.
✅ **Twin is per-USER** (`docs/decisions/twin-keying.md`, see P2) — the premise "it models *you*, one
   coherent self across the workforce" now holds in code: the interview seeds it, every NEop reads it at
   assemble, Twin Curator + Decision Shadow operate on it. So fidelity/maturity measure the **person**, not
   a per-NEop fragment — the precondition for the D90 fidelity criterion being meaningful.
🔨/⛔ **Wiring** (live-gated, server-side — NOT offline-buildable): real STM/LTM/Vault tiering (broker
   passthrough → `vault.promote`); RRF 4-backend fusion (broker is vector-only — add bm25/graph/recency);
   fidelity clock (per-**user** rolling window surfacing `curator.fidelity`); live tool binding for the
   wrappers + async cadence. (Fidelity TARGET 0.65@D90 is a learning-clock outcome, not a build.)

### P5 — The fleet 🔨/⛔
🔨 re-wrap Recon/ICD/CoS/TeamPulse onto planner→executor→verifier; build toward the catalog (each green under `nrt`).
⛔ per-NEop domain sign-off (tool allowlist + approval scopes).

### P6 — Platform layers (V2) 🔨/⛔
🔨 NE-Eval, Model Studio, Marketplace V0, the flywheel logic.
⛔ NE-QuickBuild auto-deploy = highest-risk; Integration-Receipt Allowlist policy sign-off.

## Cross-cutting gates
- **Security:** ✅ 4-layer ACL **enforcing**; **3/4 layers emit** to the unified audit from production code,
  live-proven (convex_sot/falkordb/broker via `denialsByLayer`) · 🔨 **edge** emit (needs a name→palaceId
  resolver at the edge seam — classifies but can't key yet) · ✅ secrets-out-of-code (S0.2) ·
  ✅ approval mediation wired (AwaitingApproval) · 🔨 Ed25519 ACP signing wired live · ⛔ pen-test ·
  ⛔ mTLS/TLS1.3/Megolm (infra).
- **Reliability (SLOs):** chat p95 ≤2s / NEop run p95 ≤60s / retrieval p95 ≤1.2s — measurable only on the
  deployed stack (⛔). DR drill ⛔.
- **Compliance:** DPDP/residency/SOC2/ISO — ⛔ (org + infra).

## V1 Day-90 acceptance scorecard
| Criterion | Status |
|---|---|
| ≥5 seats onboarded, twin.md v≥5 | ✅ twin is per-USER + seeded by the interview (keying done) · ⛔ live tenant to accrue versions |
| ≥3 NEops/seat in regular use | 🔨 P5 re-wrap, then ⛔ usage |
| twin fidelity ≥0.65 | ✅ measures the **person** now (per-user twin) · 🔨 P4 fidelity clock · ⛔ usage outcome |
| chat p95 ≤2s / NEop run p95 ≤60s | ⛔ deployed-stack measurement |
| **zero tenant-isolation violations 30d** | ✅ mechanism live-proven (4-layer ACL enforcing + audit replay via `denialsByLayer`, 3/4 layers emit; edge-emit 🔨) — needs ⛔ 30d live window |
| 6 meta-NEops live · dashboard · pen-test | ✅ 4 meta-NEops wrapped (+ approval/edge meta-seams) · 🔨 dashboard · ⛔ live binding + pen-test |

## Critical path to V1
**The offline-buildable runway is essentially spent** — P2 governance is wired + live-proven, the gov-flip
seam is complete, and all 4 meta-NEops are wrapped. From here the program moves by **activation** (flips +
config) and **infra**, both human-gated.
**Human (⛔), unblocks the most:** PAT rotation (30s, first) · **the governance flip** (minimal policy +
env toggles for the dogfood tenant — its whole seam is now live-proven) · embedder key · AWS infra +
`terraform apply` (→ P1, live P3, CMK) · Synapse hosts · policy sign-offs · pen-test/DR drill.
**Agent (🔨), what's left:** **edge denial emit** (a name→palaceId resolver at the edge seam — the 4th audit
layer) · P3 nc-web **UI** over the Decision-Queue API + dashboard over `denialsByLayer` · nc-channels Matrix
adapter · P5 fleet re-wrap (Recon/ICD/CoS/TeamPulse onto the proven recipe) · P6 platform layers · OPA/Rego code.

## Verdict
The **identity / audit / governance spine is production-grade, live-verified, and ACTIVATED** — the approval
engine has a durable consumer (AwaitingApproval ↔ `paused_runs`) with the human-in-the-loop **Decision Queue
loop live-proven**, **3/4 ACL layers emit** to the unified audit live (edge-emit named below), and all 4
meta-NEops are wrapped. Reaching V1 needs (a) the human ⛔ gates — chiefly the **governance flip** (cheap, its
seam is proven), the embedder, and infra — and (b) the remaining **agent product-build (edge-emit + P3 nc-web/
channels + P5 fleet)**, a multi-session effort. **"Production-ready" is the Day-90 live gate — inherently
human, NOT agent-declarable; this ledger does not claim it.** No part is faked; every item has an owner and an
acceptance criterion, and what could be proven offline or on the self-host has been — including the gaps this
completeness pass found (the Decision Queue read, the broker emit) and the one it could only name (edge emit).
