# NEOS production substrate (Terraform)

The deployment substrate for the NEOS runtime tier as code: **VPC** (public/private subnets across
≥2 AZs, single NAT) → **ALB** → **ECS Fargate** service running the runtime container → **Secrets
Manager** (empty secrets, values set out-of-band) → **IAM** (least-privilege exec/task roles) →
**CloudWatch** logs.

## Status — built to the wall, `apply` is the gate
- ✅ `terraform fmt -check` · `terraform init` · `terraform validate` all clean (offline, no AWS account).
- ⛔ `terraform plan` / `apply` need **AWS credentials + an account** — that is the human gate. `validate`
  proves the HCL is correct; it does **not** prove the infra works. Nothing here is "deployed."
- This module is the runtime tier only. The bridge (FalkorDB/Graphiti), nc-* services, Synapse, and
  managed datastores are added as further task defs / modules once the runtime tier is proven live.

## What it deliberately does NOT do (least-secrets-in-code, per S0.2)
- **No secret values** live in TF code or state. `secrets.tf` creates the secrets *empty*; you set the
  values after apply. State can still contain sensitive metadata → use an encrypted S3 backend (below).

## Apply runbook (operator — the gate)
```bash
# 0. Prereqs: AWS creds (a deploy role), an ECR repo, the runtime image pushed (S0.1 Dockerfile).
aws ecr create-repository --repository-name neos-runtime --region ap-south-1
docker build -t neos-runtime ../..          # the S0.1 Dockerfile (PR #6)
# docker tag + push to the ECR URI ...

# 1. Configure
cp terraform.tfvars.example terraform.tfvars   # fill runtime_image, convex_site_url, region
#   Recommended: an encrypted remote backend — uncomment backend "s3" in versions.tf first.

# 2. Plan + apply (THE GATE)
terraform init
terraform plan -out tf.plan        # review every resource
terraform apply tf.plan

# 3. Set the secret VALUES (never in TF). One per managed_secret_keys:
aws secretsmanager put-secret-value --secret-id neos-dogfood/ANTHROPIC_API_KEY        --secret-string "sk-ant-..."
aws secretsmanager put-secret-value --secret-id neos-dogfood/PALACE_BRIDGE_API_KEY     --secret-string "$(openssl rand -hex 24)"
# ... EMBEDDER_API_KEY, CONVEX_SELF_HOSTED_ADMIN_KEY
aws ecs update-service --cluster neos-dogfood-cluster --service neos-dogfood-runtime --force-new-deployment

# 4. Verify
curl http://$(terraform output -raw alb_dns_name)/health
```

## Before prod (additional gates)
- TLS: ACM cert + a 443 listener + HTTP→HTTPS redirect (needs a domain).
- KMS CMK for Secrets Manager + log encryption.
- Remote state (encrypted S3 + DynamoDB lock).
- Multi-AZ NAT, autoscaling, WAF, pen-test — the V1 cross-cutting gates in `docs/production-readiness.md`.
