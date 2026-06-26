# Dogfood Spine — End-to-End Deployment Runbook

**Goal:** stand up the **minimal NEOS dogfood spine** on AWS (`ap-south-1`) and get
`tools/deployed_stack_smoke.py` GREEN against it. Spine = **VPC + ALB + Convex (SoT) + runtime + bridge
(+ FalkorDB sidecar)**. Comms/audit tier (ClickHouse · NATS · Synapse · RDS · ElastiCache) is **deferred**.

**Honest framing (carried from `docs/production-readiness.md`):** a green spine smoke proves the
identity/memory/audit substrate runs live on AWS. It is **NOT** "production-ready" — that remains the
**Day-90 acceptance gate** (≥5 seats, fidelity ≥0.65, pen-test, 30-day zero-isolation-violations). This
runbook reaches a **live spine**, nothing more, and never claims otherwise.

**Account:** `071126865245` (IAM user `mansi-synlex`) · **Region:** `ap-south-1` · **Env:** `dogfood`.
**Validated:** creds OK (`sts get-caller-identity`); `terraform plan` clean (`91 add` full / ~60 spine).
**Rough cost (spine):** ~$100/mo (1 NAT ~$33 · ALB ~$20 · 3-4 Fargate tasks ~$45 · EFS/KMS/logs ~$5).

---

## The four real walls (and how the plan clears each)

| # | Wall | Resolution in this plan |
|---|------|-------------------------|
| W1 | **No local Docker** — runtime/bridge images don't exist; ECS refs are `PLACEHOLDER`. | **AWS CodeBuild** (privileged) builds from an **S3 source zip** → pushes to ECR. No local Docker. |
| W2 | **Convex backend is internal-only** (`assign_public_ip=false`, Cloud Map private DNS) — functions can't be `convex deploy`'d from this box. | The **same CodeBuild project, VPC-attached** (private subnets) runs `npx convex deploy` in-VPC against `convex.<ns>:3210`. |
| W3 | **TF is all-or-nothing (91 res)** — no spine-only switch. | New `enable_comms_tier` bool (default `true`); `count`-gate the 4 comms files; dogfood tfvars sets it `false`. Config, not `-target`. |
| W4 | **No model/embedder key** in `.env` (only Gemini + OpenRouter). | Embedder **deferred** (empty secret, `enable_bedrock=false`). Model key **deferred** — the spine smoke exercises memory/ACL/audit, **not** a live NEop model run, so it passes without one. |

Minor fix folded in: bridge Dockerfile listens on **8100**, `variables.tf` default is **8000** → align
`bridge_container_port` (and the bridge TG/health wiring) to **8100**.

---

## Phase 1 — Offline code (no cost, reversible, on a branch) — `[A]` agent-buildable
All `terraform validate`-clean before anything bills.

1. **`enable_comms_tier` flag (W3).** Add `variable "enable_comms_tier" { type = bool, default = true }`.
   Add `count = var.enable_comms_tier ? 1 : 0` to every top-level resource in `elasticache.tf` / `nats.tf` /
   `clickhouse.tf` / `synapse.tf` (29 resources) and `[0]`-index their **intra-file** references + the
   `redis_endpoint` output (which lives in `elasticache.tf`). Spine files are untouched (no spine→comms dep).
2. **Bridge port fix (W4-minor).** `bridge_container_port` default `8000` → `8100`; confirm `bridge.tf`
   target-group / container `portMappings` / Cloud Map all use the var, not a literal.
3. **Convex image → public.** Set `convex_image` (via tfvars) to `ghcr.io/get-convex/convex-backend:latest`
   (matches the `INSTANCE_NAME`/`INSTANCE_SECRET` contract in `convex.tf`). ECS pulls public GHCR directly.
4. **`terraform.tfvars` (dogfood spine).** `environment="dogfood"`, `region="ap-south-1"`,
   `enable_comms_tier=false`, `enable_bedrock=false`, `convex_image=…ghcr…`, `runtime_image`/`bridge_image`
   left as the ECR URIs (filled after Phase 3), `domain_name`/`route53_zone_id` blank (HTTP-only dogfood).
5. **Build tooling** (`infra/build/`): `buildspec-runtime.yml`, `buildspec-bridge.yml`,
   `buildspec-convex-deploy.yml`, and `bootstrap-codebuild.sh` (creates the S3 source bucket, CodeBuild
   role+policy, and a VPC-attached project). Authored here; **run** in Phase 3 (bills).
6. `terraform fmt` + `validate` clean → commit on `deploy/dogfood-spine` → PR.

## Phase 2 — Remote state (recommended, tiny cost) — `[U]` gate
Local state on a WSL box is a single point of loss. Create an encrypted S3 bucket + DynamoDB lock,
uncomment `backend "s3"` in `versions.tf`, `terraform init -migrate-state`. (Skippable for a first throwaway
apply; do before any real iteration.)

## Phase 3 — ECR + images (CodeBuild) — `[U]` gate (bills ~cents)
1. Create the 2 ECR repos (`-target=aws_ecr_repository.runtime -target=aws_ecr_repository.bridge`, or CLI).
2. `bootstrap-codebuild.sh` → S3 bucket + CodeBuild project (privileged, VPC-attached to the private subnets).
3. **runtime image:** zip repo root (respecting `.dockerignore`) → S3 → `start-build` w/ `buildspec-runtime`
   → pushes `…/neos-dogfood-runtime:<gitsha>`. Verify `aws ecr describe-images`.
4. **bridge image:** zip `../Mempalace_NEOS/services` → S3 → `buildspec-bridge` → `…/neos-dogfood-bridge:<sha>`.
5. Pin both image vars in `terraform.tfvars` to the pushed **digests**.

## Phase 4 — Apply the spine — `[U]` GATE (real billing starts) — **CHECKPOINT before running**
1. `terraform plan -out tf.plan` (expect ~60 resources, comms tier absent) → review every line.
2. `terraform apply tf.plan`.
3. **Secret values** (never in TF state): `CONVEX_INSTANCE_SECRET` = `openssl rand -hex 32`,
   `CONVEX_SELF_HOSTED_ADMIN_KEY` (from the convex backend once up, or pre-generated per its scheme),
   `PALACE_BRIDGE_API_KEY` = `openssl rand -hex 24`. `ANTHROPIC_API_KEY` / `EMBEDDER_API_KEY` left **empty**
   (deferred). `aws secretsmanager put-secret-value` each.
4. `aws ecs update-service --force-new-deployment` for convex → bridge → runtime (in that order).

## Phase 5 — Convex functions + bring-up (W2) — `[U]`
1. Wait: Convex service healthy (Cloud Map `convex.<ns>` resolves, :3210 up).
2. **Deploy Mempalace functions in-VPC:** CodeBuild `buildspec-convex-deploy` runs
   `CONVEX_SELF_HOSTED_URL=http://convex.<ns>:3210 CONVEX_SELF_HOSTED_ADMIN_KEY=… npx convex deploy -y`
   from `../Mempalace_NEOS` (zipped to S3). This is the only way to reach the internal backend.
3. Bridge + runtime healthy on the ALB (`/health` 200).

## Phase 6 — Verify (the definition of done for this runbook) — `[A]` to run
`NEOS_SMOKE_API_URL=http://<alb_dns> NEOS_SMOKE_SITE_URL=http://convex…:3211
NEOS_SMOKE_ADMIN_KEY=… python3 tools/deployed_stack_smoke.py` → **7/7** (tenant→palaceId, broker
write/retrieve, broker denial, paused_runs round-trip, denialsByLayer, twin per-user). Note: the smoke
runs from inside the VPC (CodeBuild/bastion) since Convex `.site` is internal.

## Phase 7 — Honest status — `[A]`
Update `docs/production-readiness.md` (P0 "live spine on AWS" — NOT Day-90) + memory. Record the deferred
activation gates below; none are faked, each has an owner.

---

## Deferred activation gates (named, not hidden — `[U]`)
- **Embedder** (Gemini key present, deferred by choice) — set `EMBEDDER_API_KEY` + re-enable vectorization.
- **Model key** — no Anthropic key in `.env`; OpenRouter present. Needed for live **NEop dispatch** (T9),
  not the spine smoke. Wire `ANTHROPIC_API_KEY` (or an OpenRouter-gateway shim) at activation.
- **Comms/audit tier** — flip `enable_comms_tier=true` + apply (ClickHouse/NATS/Synapse/RDS/ElastiCache).
- **TLS** — set `domain_name` + `route53_zone_id` (ACM/443/redirect already gated-in).
- **Signed identity (Gate D / S0.3)** — `X-NEop-Identity` HMAC/Ed25519 + pen-test.
- **Single-writer Convex** — `desired_count=1` + EFS-SQLite; a Postgres-backend swap precedes any 2nd instance.
- **Remote state, multi-AZ NAT, Redis HA, NATS JetStream durability, Synapse public ingress** — pre-prod.
- **The governance flip** — set `docs/decisions/approval-policy-v1.md` + `BRIDGE_IDENTITY_ENABLED` on.

## Rotation reminders (security)
`.env` holds live AWS + OpenRouter + Gemini keys. The GitHub PAT and OpenRouter key were transcript-exposed
earlier → **rotate**. Never commit `.env` (confirm `.gitignore`). Secrets set out-of-band only.
