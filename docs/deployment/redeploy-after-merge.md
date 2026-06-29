# Re-deploy the live spine after the 2026-06-29 merges — operator recipe

**Status: NOT executed. This is the replay recipe for YOU to run on the box.** A re-deploy touches the
**live, billing** dogfood spine (account 071126865245, ap-south-1) and is a ⛔ human gate. There is no
Docker on the WSL dev box, so image builds + `terraform apply` run on the target host / CI, not from here.

## What merged (and what each needs to go live)
| Merged to `main` | To take effect on the live spine |
|---|---|
| **#46** M2 — runtime LLM → OpenRouter (`CLASSIFIER_PROVIDER` env in `ecs.tf`) | `terraform apply` (new task-def env) **+** set the `OPENROUTER_API_KEY` secret value |
| **#47** M3·T3.1/T3.2 — OIDC→ECR pipeline + phase tfvars | `terraform apply` the IAM (`gha-oidc.tf`), then run the image workflows |
| **#48** jcode T5/T6 + T0 run-book | rides in the next **runtime image** build (adapter code) — no live effect until jcode dispatch (T9, gated) |
| **#27** (Mempalace) bridge image CI workflow | enables the keyless bridge image build; no live effect until applied |

**HELD — do NOT deploy:** **M1 #26 (Gemini @768)** stays out of `main` and off the live spine — the
no-NAT spine can't reach Gemini and runs **Titan @1024**. Confirm before every apply: `git show
main:convex/schema.ts | grep dimensions` in Mempalace must read **1024**. Promote M1 only after the NAT decision.

## 0. Pre-flight (on the box, with AWS creds configured)
```bash
aws sts get-caller-identity                      # creds OK, account 071126865245
git -C NEURAL-ops      rev-parse --short main     # the code you're shipping
git -C Mempalace_NEOS  show main:convex/schema.ts | grep dimensions   # MUST be 1024 (M1 held)
```

## 1. Activate the keyless image pipeline (one-time, cheap — IAM only) — ⛔
```bash
cd NEURAL-ops/infra/terraform
terraform init
terraform apply -target=aws_iam_openid_connect_provider.github \
                -target=aws_iam_role.gha_ecr_push \
                -target=aws_iam_role_policy.gha_ecr_push     # creates gha-ecr-push (no ongoing cost)
```

## 2. Build + push the new images (keyless, via the merged workflows)
```bash
gh workflow run build-push-ecr.yml -R mansi118/NEURAL-ops       # runtime image (T5/T6 adapter + M2)
gh workflow run build-push-ecr.yml -R mansi118/Mempalace_NEOS   # bridge image
# Watch, then capture the IMMUTABLE digests each prints (repos are immutable — pin digests, not :latest):
gh run watch -R mansi118/NEURAL-ops ; gh run watch -R mansi118/Mempalace_NEOS
aws ecr describe-images --repository-name neos-dogfood-runtime --query 'imageDetails[0].imageDigest' --output text
aws ecr describe-images --repository-name neos-dogfood-bridge  --query 'imageDetails[0].imageDigest' --output text
```

## 3. Pin the digests + set the new secret
```bash
# In NEURAL-ops/infra/terraform/terraform.tfvars (gitignored), set:
#   runtime_image = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-runtime@sha256:<digest>"
#   bridge_image  = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-bridge@sha256:<digest>"
#   llm_provider  = "openrouter"     # M2 default; runtime CLASSIFIER_PROVIDER follows it
# M2 needs the key value (never in TF state):
aws secretsmanager put-secret-value --secret-id neos-dogfood/OPENROUTER_API_KEY --secret-string "<sk-or-...>"
```

## 4. Plan + apply the live spine — ⛔ CHECKPOINT (real billing change)
```bash
cd NEURAL-ops/infra/terraform
terraform plan -out tf.plan      # REVIEW: expect runtime task-def change (image + CLASSIFIER_PROVIDER), no tier add
terraform apply tf.plan
# roll the services to the new task defs (convex unchanged → skip; bridge then runtime):
aws ecs update-service --cluster neos-dogfood-cluster --service neos-dogfood-bridge   --force-new-deployment
aws ecs update-service --cluster neos-dogfood-cluster --service neos-dogfood-runtime  --force-new-deployment
```

## 5. Convex functions — only if changed
Mempalace `main` changed only CI (the bridge workflow) — **no `convex deploy` needed**. If a later merge
touches `convex/`, deploy in-VPC (the backend is internal): CodeBuild `buildspec-convex-deploy` runs
`CONVEX_SELF_HOSTED_URL=http://convex.<ns>:3210 npx convex deploy -y` from `Mempalace_NEOS`.

## 6. Verify (the definition of done for a re-deploy)
```bash
# from inside the VPC (CodeBuild/bastion — Convex .site is internal):
NEOS_SMOKE_API_URL=http://<alb_dns> NEOS_SMOKE_SITE_URL=http://convex...:3211 NEOS_SMOKE_ADMIN_KEY=... \
  python3 tools/deployed_stack_smoke.py     # expect 7/7
```

## What this re-deploy is NOT
A green re-deploy ships the merged code to the live spine. It is **not** "production-ready" — that remains
the **Day-90 acceptance gate** (≥5 seats · fidelity ≥0.65 · pen-test · 30-day zero-isolation-violations),
which no deploy can satisfy. It also does **not** turn on live NEop dispatch (that's the jcode adapter +
T0/T7/T9 gates), the comms tier (`enable_comms_tier`), the governance flip (`enable_bridge_identity`),
TLS, or M1/Gemini. Each remains an explicit, owned gate — see `docs/production-readiness.md`.
