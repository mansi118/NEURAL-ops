#!/usr/bin/env bash
# Deploy the Mempalace Convex functions to the INTERNAL self-hosted backend (no public IP).
# Runs on a VPC-attached CodeBuild project so it can reach convex.<ns>:3210 in-VPC.
# Run AFTER `terraform apply` of the spine (it reads VPC config from terraform outputs).
#
# Usage:  ./convex-deploy.sh
# Env:    REGION (ap-south-1) · ENVIRONMENT (dogfood) · MEMPALACE_DIR (../../../Mempalace_NEOS)
set -euo pipefail

REGION="${REGION:-ap-south-1}"
ENVIRONMENT="${ENVIRONMENT:-dogfood}"
PROJECT="${PROJECT:-neos}"
NAME="${PROJECT}-${ENVIRONMENT}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(cd "$HERE/../terraform" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
MEMPALACE_DIR="${MEMPALACE_DIR:-$REPO_ROOT/../Mempalace_NEOS}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${NAME}-codebuild-src-${ACCOUNT_ID}"
ROLE="${NAME}-codebuild-role"
PROJECT_NAME="${NAME}-convex-deploy"

log() { printf '\033[1;35m[convex-deploy]\033[0m %s\n' "$*"; }
tfout() { ( cd "$TF_DIR" && terraform output -raw "$1" ); }
tfjson() { ( cd "$TF_DIR" && terraform output -json "$1" ); }

VPC_ID="$(tfout vpc_id)"
CONVEX_API_URL="$(tfout convex_api_url)"
ADMIN_SECRET_ARN="$(tfjson secret_arns | python3 -c 'import json,sys;print(json.load(sys.stdin)["CONVEX_SELF_HOSTED_ADMIN_KEY"])')"
SUBNETS="$(tfjson private_subnet_ids | python3 -c 'import json,sys;print(",".join(json.load(sys.stdin)))')"

log "VPC=$VPC_ID  Convex=$CONVEX_API_URL  subnets=$SUBNETS"

# Dedicated egress-only SG for the CodeBuild ENI (Convex SG already allows the whole VPC CIDR inbound).
SG_ID="$(aws ec2 describe-security-groups --filters Name=group-name,Values="${NAME}-codebuild-sg" Name=vpc-id,Values="$VPC_ID" \
         --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)"
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID="$(aws ec2 create-security-group --group-name "${NAME}-codebuild-sg" \
            --description "NEOS CodeBuild ENI (egress only)" --vpc-id "$VPC_ID" --query GroupId --output text)"
  log "created CodeBuild SG $SG_ID (default egress-all)"
fi

# Allow the role to read the admin-key secret + manage ENIs for VPC config (add to the existing inline policy).
aws iam put-role-policy --role-name "$ROLE" --policy-name "${NAME}-convex-deploy-policy" --policy-document "$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":"${ADMIN_SECRET_ARN}"},
 {"Effect":"Allow","Action":["ec2:CreateNetworkInterface","ec2:DescribeNetworkInterfaces","ec2:DeleteNetworkInterface","ec2:DescribeSubnets","ec2:DescribeSecurityGroups","ec2:DescribeVpcs","ec2:DescribeDhcpOptions","ec2:CreateNetworkInterfacePermission"],"Resource":"*"}
]}
JSON
)"
sleep 5

SUBNETS_JSON="$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1].split(",")))' "$SUBNETS")"
cfg=$(cat <<JSON
{"name":"${PROJECT_NAME}",
 "source":{"type":"S3","location":"${BUCKET}/placeholder.zip","buildspec":"infra/build/buildspec-convex-deploy.yml"},
 "artifacts":{"type":"NO_ARTIFACTS"},
 "environment":{"type":"LINUX_CONTAINER","image":"aws/codebuild/standard:7.0","computeType":"BUILD_GENERAL1_SMALL","privilegedMode":false,
   "environmentVariables":[
     {"name":"CONVEX_SELF_HOSTED_URL","value":"${CONVEX_API_URL}","type":"PLAINTEXT"},
     {"name":"CONVEX_SELF_HOSTED_ADMIN_KEY","value":"${ADMIN_SECRET_ARN}","type":"SECRETS_MANAGER"}]},
 "vpcConfig":{"vpcId":"${VPC_ID}","subnets":${SUBNETS_JSON},"securityGroupIds":["${SG_ID}"]},
 "serviceRole":"arn:aws:iam::${ACCOUNT_ID}:role/${ROLE}"}
JSON
)
if aws codebuild batch-get-projects --names "$PROJECT_NAME" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$PROJECT_NAME"; then
  aws codebuild update-project --cli-input-json "$cfg" >/dev/null
else
  aws codebuild create-project --cli-input-json "$cfg" >/dev/null
fi

log "zipping Mempalace ($MEMPALACE_DIR) → S3"
zip="/tmp/mempalace-src.zip"
( cd "$MEMPALACE_DIR" && rm -f "$zip" && zip -qr "$zip" . -x '*.git*' 'node_modules/*' )
KEY="src/convex-$(date +%s 2>/dev/null || echo manual).zip"
aws s3 cp "$zip" "s3://${BUCKET}/${KEY}" >/dev/null

log "starting in-VPC convex deploy"
bid=$(aws codebuild start-build --project-name "$PROJECT_NAME" \
      --source-location-override "${BUCKET}/${KEY}" --source-type-override S3 \
      --query 'build.id' --output text)
log "build id $bid — polling…"
while :; do
  st=$(aws codebuild batch-get-builds --ids "$bid" --query 'builds[0].buildStatus' --output text)
  case "$st" in
    SUCCEEDED) log "Convex functions deployed."; break ;;
    IN_PROGRESS) sleep 12 ;;
    *) log "convex deploy $st — see CodeBuild logs for $bid"; exit 1 ;;
  esac
done
