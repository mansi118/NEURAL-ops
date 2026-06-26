# NEOS image build + Convex deploy (no local Docker)

Builds the custom container images on **AWS CodeBuild** (so no Docker is needed locally) and deploys the
Convex functions to the **internal** self-hosted backend from inside the VPC. See the full sequence in
`docs/deployment/dogfood-spine-runbook.md`.

## Prereqs
- AWS creds in the environment (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), region `ap-south-1`.
- `terraform init` already run in `../terraform`.
- The Mempalace repo checked out next to this one (`../../../Mempalace_NEOS`) for the bridge image + Convex functions.

## Sequence
```bash
cd infra/build

# 1. One-time: ECR repos (via terraform -target) + S3 source bucket + CodeBuild role/project.
./build.sh bootstrap

# 2. Build + push the custom images (CodeBuild; prints  <repo>@sha256:<digest>).
./build.sh runtime bridge

# 3. Pin the printed image digests into ../terraform/terraform.tfvars (runtime_image / bridge_image),
#    then apply the spine:
cd ../terraform
cp dogfood-spine.tfvars.example terraform.tfvars      # fill runtime_image / bridge_image
terraform plan -out tf.plan && terraform apply tf.plan

# 4. Set the secret VALUES (never in TF state):
aws secretsmanager put-secret-value --secret-id neos-dogfood/CONVEX_INSTANCE_SECRET       --secret-string "$(openssl rand -hex 32)"
aws secretsmanager put-secret-value --secret-id neos-dogfood/PALACE_BRIDGE_API_KEY        --secret-string "$(openssl rand -hex 24)"
aws secretsmanager put-secret-value --secret-id neos-dogfood/CONVEX_SELF_HOSTED_ADMIN_KEY --secret-string "<convex-admin-key>"
#   ANTHROPIC_API_KEY / EMBEDDER_API_KEY left empty (deferred).

# 5. Deploy the Convex functions to the internal backend (VPC-attached CodeBuild):
cd ../build && ./convex-deploy.sh

# 6. Force-new-deployment so the services pick up images/functions, then run the smoke (from in-VPC).
```

## Why CodeBuild
- **No local Docker** on the dev box → image builds run on CodeBuild (`privilegedMode=true`).
- **Convex is internal** (`assign_public_ip=false`, Cloud Map private DNS) → `convex deploy` must run
  in-VPC; `convex-deploy.sh` creates a VPC-attached project on the private subnets.

## Cost / cleanup
CodeBuild is ~$0.005/build-min (general1.small); a handful of builds is cents. The S3 source bucket and
CodeBuild project are negligible. Teardown: `aws codebuild delete-project`, empty+delete the bucket,
`aws iam delete-role-policy`/`delete-role`. ECR repos are managed by terraform (`terraform destroy`).
