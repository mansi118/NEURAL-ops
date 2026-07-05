# ADR — The canonical Matrix homeserver is the existing `matrix.neuraledge.in` (EC2), NOT the Fargate `synapse.tf`

> **Status:** DECIDED 2026-07-05 — verified by live probe against account `071126865245`.
> **Owner:** ML · **Confidentiality:** INTERNAL — NeuralEDGE
> **Supersedes:** the "stand up Synapse via `terraform apply -var-file=phase2.tfvars`" step in the tactical
> Matrix runbooks (`element-first-contact-runbook.md`, `neos-matrix-integration-plan.md`,
> `nc-channels-transport-deploy-design.md`, `launch-checklist.md` Phase 2).

## Why this ADR exists
The record carried an **unreconciled contradiction** about where Matrix/Synapse lives, and it cost a real,
billed mistake:
- **Tactical runbooks** (which an executing session follows) walk through activating the **Fargate**
  `synapse.tf` — G-A/B/C, `phase2.tfvars`, the "irreversible `server_name` byte," a box window to stand up
  Synapse + RDS + EFS.
- **Strategic docs** (`activation-timeline.md:74`, `go-live-checklist.md:19`, `neos-ui-matrix-plan.md:34`,
  `path-to-day-90.md:47`, `neos-matrix-integration-plan.md:44`) say the homeserver **already exists →
  reuse `matrix.neuraledge.in`, skip standing one up.**

No doc ever declared which wins. On 2026-07-05 a session followed the tactical path and ran
`terraform apply -var-file=phase2.tfvars`, standing up a **second, redundant, broken** Fargate Synapse
(+ RDS/EFS/NATS/ClickHouse) in the spine VPC — then reverted it. This ADR ends the ambiguity on evidence.

## What the live account actually shows (verified 2026-07-05, file:line-equivalent probes)
- `matrix.neuraledge.in` resolves to **`13.201.114.109`** = the **`matrix-server` EC2 box** (`i-0dcfbf5e0eecb4dcd`, running since 2026-04-04, **default VPC `172.31/16`**).
- Federation `GET :8448/_matrix/federation/v1/version` → **`{"server":{"name":"Synapse","version":"1.150.0"}}`** — a real, current Synapse.
- Client API (`/_matrix/client/versions`) live through **v1.12**; `.well-known/matrix/server` → `matrix.neuraledge.in:8448`. TLS + federation + delegation all configured and working. Public on 80/443/8448; SSH `:22` restricted to `128.185.163.10/32`, key `aws-server`.
- The Fargate `synapse.tf` build is in the **spine VPC `10.40/16`**, internal-only, and when applied it **failed to start** (exec-role lacks `secretsmanager:GetSecretValue` on the RDS-managed secret). It is a redundant parallel build of something that already exists and works.

## Decision
1. **`matrix.neuraledge.in` (the EC2 `matrix-server` Synapse 1.150.0) is the canonical NEOS homeserver.**
   `server_name` is already `matrix.neuraledge.in`, baked and correct. Matrix integration **registers against
   it**; it does **not** build a new one.
2. **The Fargate `synapse.tf` (+ its RDS/EFS) is retired for Matrix.** It stays in the repo history but MUST
   NOT be applied as the homeserver. **Follow-up TF change:** gate the Synapse resources *out* of the comms
   tier (they should not ride `enable_comms_tier`), so a `phase2` apply brings up only the legitimate comms
   components (**NATS · Redis/ElastiCache · ClickHouse**) and never a second Synapse. Until that refactor
   lands, **do not `terraform apply -var-file=phase2.tfvars`** without first confirming `synapse.tf` is
   excluded.
3. **The G-A / G-B saga is moot.** G-A (`server_name` immutable byte) — already baked on the live HS. G-B
   (public ingress) — already public. Both were solving problems the existing homeserver doesn't have.

## Consequences — the corrected integration shape
Registering `nc-channels` as an Application Service against `matrix.neuraledge.in`:
- **Needs admin access to the `matrix-server` EC2 box** (SSH via `aws-server` key from the allowed IP, or an
  equivalent path) to add the AS `registration.yaml` to `homeserver.yaml` (`app_service_config_files`) and
  restart Synapse. **This is the `[U]` gate** that replaces the entire Fargate box window.
- **Cross-VPC networking is the one real design question.** `nc-channels` runs the orchestrator in-process
  (`frontdoor/orchestrator.py handle → dispatch`) and must reach **both** the public Synapse (default VPC)
  **and** the palace `/mcp` (Convex, internal to the spine VPC `10.40`, Cloud Map `convex.<ns>:3211`).
  Options to design: co-locate `nc-channels` on/near `matrix-server` with a peered/whitelisted path to the
  palace; or run it in the spine VPC with a reachable inbound endpoint for Synapse's AS transactions. Decide
  and record before building.
- **Sequencing (unchanged):** Bar 1 (echo, pipe-connected) is provable against the real Synapse once the AS
  is registered and reachability is solved. Bar 2 (memory-backed reply) still needs M1b / GAP-1
  (`pi-neop-runtime`) per the reconciled launch checklist. Matrix transport carries intelligence; it does not
  create it.

## Retargeting (docs to correct so the contradiction can't recur)
`element-first-contact-runbook.md`, `neos-matrix-integration-plan.md`,
`nc-channels-transport-deploy-design.md`, `launch-checklist.md` (Phase 2): replace "apply the Fargate
Synapse (G-A/B/C, phase2)" with "register the AS against the existing `matrix.neuraledge.in`." Tracked as a
follow-up; this ADR is the source of truth in the meantime.
