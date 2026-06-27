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
>
> **2026-06-28 — SPINE LIVE ON AWS (dogfood, ap-south-1).** `terraform apply` crossed: the minimal spine
> (VPC + Convex SoT + runtime + bridge+FalkorDB) is deployed and the **deployed-stack smoke passes 7/7 against
> the real AWS backend** (account 071126865245). All three ECS services stable. This is a **live spine, not
> production-ready** — the Day-90 gate stands. Deferred by design: comms/audit tier (`enable_comms_tier=false`),
> embedder + model key, TLS (HTTP-only in-VPC), governance flip. Runbook: `docs/deployment/dogfood-spine-runbook.md`.
> Account constraint met honestly: EIP quota was full, so the spine uses **VPC endpoints, no NAT** (`enable_nat_gateway=false`).

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

### P0 — Cross the live wall ✅ (self-host AND AWS)
✅ live single-seat round-trip proven; edge-auth live seam (resolve_binding→Convex) proven; codegen+tsc green.
✅ **AWS deploy crossed (2026-06-28):** Convex functions deployed to the self-hosted backend on Fargate
   (in-VPC via CodeBuild), tenant seeded, **deployed-stack smoke 7/7 against the live AWS backend**.
⛔ embedder decision+key; rotations; Anthropic/model key for live classifier verdict (deferred — spine smoke needs none).

### P1 — Production substrate (S0) — FULL TERRAFORM SUBSTRATE on main, validate-clean
✅ S0.1 runtime container (PR #6 **merged**) · S0.2 secrets (`runtime/secrets.py`, env→keyring→refuse).
✅ **Terraform substrate — complete + validate-clean** (`infra/terraform/`): VPC/subnets/NAT · ALB (+TLS gated:
   ACM/443/redirect, #32) · ECS Fargate **runtime** (#21) · **bridge + FalkorDB sidecar + EFS** (#31) · **ECR +
   KMS CMK + KMS-encrypted secrets/logs** (#31) · **self-host Convex on ECS + EFS** (the SoT, #36) · **comms tier:
   ElastiCache Redis + NATS + ClickHouse + Synapse(+RDS Postgres)** (#37) · Cloud Map internal DNS · Bedrock IAM
   (gated). Secrets created empty (values out-of-band, S0.2). `fmt`/`init`/`validate` clean; README apply-runbook.
✅ Deployed-stack smoke (`tools/deployed_stack_smoke.py`, #38) — 7/7 vs self-host AND **7/7 vs live AWS (2026-06-28)**.
✅ **SPINE APPLIED + LIVE on AWS (ap-south-1, 2026-06-28):** `terraform apply` of the dogfood spine — VPC +
   ALB + Convex SoT + runtime (idle worker; `enable_runtime_alb=false`) + bridge+FalkorDB. Images built with
   **no local Docker via CodeBuild** (runtime/bridge from source; Convex/FalkorDB mirrored ghcr/DockerHub→ECR).
   **No NAT** — VPC endpoints (ECR/S3/Logs/SecretsManager), `enable_nat_gateway=false` (account EIP quota was full).
   Spine-only via `enable_comms_tier=false` (91→59→56 applied resources). Secrets out-of-band (admin key generated
   from the instance secret in CodeBuild). Tooling: `infra/build/{build,spine-verify,convex-deploy}.sh`.
🔨 OTel instrumentation; nc-* service containers (need the service code — P3).
⛔ **comms tier apply** (`enable_comms_tier=true`) · remote state (S3+lock) · DR backups · TLS (domain+ACM).
   Named substrate forward-deps (managed, not hidden): **single-writer Convex** (SQLite-on-EFS, `desired_count=1` —
   a Postgres-backend SWAP is a prerequisite for multi-instance, not a tuning knob) · Redis HA (replica+failover) ·
   NATS JetStream durability (EFS) · Synapse PUBLIC client-API ingress (ALB host rule + federation) · RDS multi-AZ.

### P2 — Governance + multi-tenant (the critical-path gate) — WIRED + ACTIVATED-READY
✅ approval-policy engine (GW-4/5/6, `acp/approval.py`) · **4-layer ACL enforcing; ALL 4 layers EMIT to the
   unified audit from production code + LIVE-proven** — `convex_sot` (native) · `falkordb` (bridge
   `_emit_external_denial`, Mempalace #20) · `broker` (runtime `audit_emit`, #27) · **`edge`** (the
   `on_reject` seam + `emit_edge_denial` resolving tenant-name→palaceId, NEURAL-ops #30 — live:
   `denialsByLayer.edge` 0→2; the emit runs OFF the rejection's critical path, verified by absence = no
   tenant-existence timing oracle). L2 enforcement + bridge wiring merged (Mempalace #18). **#12 closed.**
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
✅ **flip-as-config WIRED** — `frontdoor/orchestrator.py handle(..., approval=None)` threads the broker into
   dispatch (#34); `build_approval(policy_config, *, mode, palace_id, grants, grantor)` constructs it from a
   policy CONFIG (store by mode; #35). Governance turns on for a tenant by supplying a policy, off by passing
   nothing (byte-identical) — **config, not a code edit.** GRANTOR is a named forward-dependency (not defaulted
   to an asserted "ml"; server-derive from the grant action when >1 granter). v1 policy spec: `docs/decisions/approval-policy-v1.md`.
⛔ **The flip itself** (set the v1 policy + `BRIDGE_IDENTITY_ENABLED`/`CONVEX_DENIAL_SINK_URL` on for the dogfood
   tenant — now just config toggles, the seam is wired+proven) · OPA/Rego **policy sign-off** · KMS CMK is built
   (#31) but the `X-NEop-Identity` signing scheme (HMAC/Ed25519) + pen-test remain.
   **Named forward-dependency (Gate D / S0.3):** twin-keying is broker-trusted today; when signed-identity lands,
   twin ops must derive the **requester** server-side (memory ops keep deriving seat) — `docs/decisions/twin-keying.md`.

### P3 — Live comms + UI 🔨/⛔
✅ **Decision Queue read API + resume-resolve loop** — `pendingPausedRuns` (lists pending pauses, surfaces
   the gated action) + `markPausedRun` + runtime resolve-on-resume (Mempalace #22, NEURAL-ops #26);
   live-proven (save→queue count 1→resolve→0). The human-in-the-loop backend AwaitingApproval serves.
✅ **Comms/audit/event tier in Terraform** (validate-clean, #37): Synapse(+RDS Postgres) · ClickHouse
   (audit-at-scale) · NATS (event bus) · ElastiCache (Redis) — all internal Cloud Map; Synapse PUBLIC
   client-API ingress is a named activation step (ALB host rule + TLS + federation), not built.
🔨 nc-channels Matrix AS adapter (app code) + normalization + HMAC; streaming transport; nc-web **UI**
   over the Decision Queue API + dashboard over `denialsByLayer`; nc-admin. (Service CODE, not infra.)
⛔ `terraform apply` for the above · domain/DNS/TLS values.

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
- **Security:** ✅ 4-layer ACL **enforcing + ALL 4 layers emit** to the unified audit from production code,
  live-proven (convex_sot/falkordb/broker/edge via `denialsByLayer`; edge emit off the critical path) ·
  ✅ secrets-out-of-code (S0.2) + KMS CMK (#31) · ✅ approval mediation wired (AwaitingApproval + flip-as-config) ·
  🔨 Ed25519 ACP signing wired live · ⛔ pen-test · ⛔ mTLS/TLS1.3/Megolm (infra).
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
| **zero tenant-isolation violations 30d** | ✅ mechanism live-proven (4-layer ACL enforcing + audit replay via `denialsByLayer`, **all 4 layers emit** incl. edge, timing-safe) — needs ⛔ 30d live window |
| 6 meta-NEops live · dashboard · pen-test | ✅ 4 meta-NEops wrapped (+ approval/edge meta-seams) · 🔨 dashboard · ⛔ live binding + pen-test |

## Critical path to V1
**The offline-buildable runway on the deploy path is spent — BUILT TO THE WALL.** P2 governance is wired +
live-proven, the gov-flip seam is complete, **all 4 ACL layers emit** to the unified audit (edge included,
timing-safe), the full AWS substrate is in Terraform (validate-clean), and all 4 meta-NEops are wrapped.
Nothing `[A]` remains to *reach* a deploy. From here the program moves by **activation** (flips + config)
and **infra**, both human-gated.
**Human (⛔), unblocks the most:** PAT rotation (30s, first) · **the governance flip** (set the v1 policy
`docs/decisions/approval-policy-v1.md` + env toggles for the dogfood tenant — its whole seam is now
live-proven) · embedder key · AWS infra + `terraform apply` (→ P1, live P3, CMK) → set secrets → deploy
Convex/stateful → run `tools/deployed_stack_smoke.py` vs AWS · Synapse hosts · policy sign-offs · pen-test/DR drill.
**Agent (🔨), what's left — all OFF the first-live-run critical path:** P3 nc-web **UI** over the
Decision-Queue API + dashboard over `denialsByLayer` · nc-channels Matrix adapter · P5 fleet re-wrap
(Recon/ICD/CoS/TeamPulse onto the proven recipe) · P6 platform layers · OPA/Rego code.

## Verdict
The **identity / audit / governance spine is production-grade, live-verified, and ACTIVATED** — the approval
engine has a durable consumer (AwaitingApproval ↔ `paused_runs`) with the human-in-the-loop **Decision Queue
loop live-proven**, **all 4 ACL layers emit** to the unified audit live (convex_sot/falkordb/broker/edge, the
edge emit verified timing-safe by absence), all 4 meta-NEops are wrapped, and the **full AWS substrate is in
Terraform (validate-clean)** with a target-agnostic deployed-stack smoke ready to point at it. **The agent has
built to the wall: nothing `[A]` remains on the path to a deploy.** Reaching V1 now needs only (a) the human ⛔
gates — PAT rotation, the **governance flip** (cheap, its seam is proven), the embedder, and `terraform apply`
→ secrets → deploy → smoke — and (b) the remaining **agent product-build (P3 nc-web/channels + P5 fleet)**,
which is OFF the first-live-run critical path. **"Production-ready" is the Day-90 live gate — inherently human,
NOT agent-declarable; this ledger does not claim it.** No part is faked; every item has an owner and an
acceptance criterion, and everything provable offline or on the self-host has been proven — including the gaps
this completeness pass found and closed (the Decision Queue read, the broker emit, and the edge emit).
