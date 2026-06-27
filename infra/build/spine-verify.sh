#!/usr/bin/env bash
# Deploy Convex functions + seed tenant + run the deployed-stack smoke — all on a VPC-attached
# CodeBuild (Convex is internal-only). Offline: bundles Mempalace node_modules; runtime.memory is
# stdlib-only. Run AFTER the spine apply + Convex is up. Usage: ./spine-verify.sh
set -euo pipefail
REGION="${REGION:-ap-south-1}"; ENVIRONMENT="${ENVIRONMENT:-dogfood}"; PROJECT="${PROJECT:-neos}"
NAME="${PROJECT}-${ENVIRONMENT}"; CLIENT="${SMOKE_CLIENT:-neuraledge}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(cd "$HERE/../terraform" && pwd)"; REPO_ROOT="$(cd "$HERE/../.." && pwd)"
MEMPALACE_DIR="${MEMPALACE_DIR:-$REPO_ROOT/../Mempalace_NEOS}"
ACCT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${NAME}-codebuild-src-${ACCT}"; ROLE="${NAME}-codebuild-role"; PROJECT_NAME="${NAME}-spine-verify"
log(){ printf '\033[1;32m[spine-verify]\033[0m %s\n' "$*"; }
tfout(){ ( cd "$TF_DIR" && terraform output -raw "$1" ); }
tfjson(){ ( cd "$TF_DIR" && terraform output -json "$1" ); }

VPC_ID="$(tfout vpc_id)"; API_URL="$(tfout convex_api_url)"; SITE_URL="$(tfout convex_site_url)"
ADMIN_ARN="$(tfjson secret_arns | python3 -c 'import json,sys;print(json.load(sys.stdin)["CONVEX_SELF_HOSTED_ADMIN_KEY"])')"
SUBNETS="$(tfjson private_subnet_ids | python3 -c 'import json,sys;print(",".join(json.load(sys.stdin)))')"
log "VPC=$VPC_ID API=$API_URL SITE=$SITE_URL"

# egress-only CodeBuild SG
SG_ID="$(aws ec2 describe-security-groups --filters Name=group-name,Values="${NAME}-codebuild-sg" Name=vpc-id,Values="$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)"
if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID="$(aws ec2 create-security-group --group-name "${NAME}-codebuild-sg" --description "NEOS CodeBuild ENI egress only" --vpc-id "$VPC_ID" --query GroupId --output text)"
  log "created CodeBuild SG $SG_ID"
fi
# role needs EC2 ENI (VPC) + read the admin secret (kms already granted)
aws iam put-role-policy --role-name "$ROLE" --policy-name "${NAME}-vpcbuild-policy" --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"ec2:CreateNetworkInterface\",\"ec2:DescribeNetworkInterfaces\",\"ec2:DeleteNetworkInterface\",\"ec2:DescribeSubnets\",\"ec2:DescribeSecurityGroups\",\"ec2:DescribeVpcs\",\"ec2:DescribeDhcpOptions\",\"ec2:CreateNetworkInterfacePermission\"],\"Resource\":\"*\"}]}"
sleep 5

SUBNETS_JSON="$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1].split(",")))' "$SUBNETS")"
cfg=$(cat <<JSON
{"name":"${PROJECT_NAME}",
 "source":{"type":"S3","location":"${BUCKET}/placeholder.zip"},
 "artifacts":{"type":"NO_ARTIFACTS"},
 "environment":{"type":"LINUX_CONTAINER","image":"aws/codebuild/standard:7.0","computeType":"BUILD_GENERAL1_MEDIUM","privilegedMode":false,
   "environmentVariables":[
     {"name":"CONVEX_API_URL","value":"${API_URL}","type":"PLAINTEXT"},
     {"name":"CONVEX_SITE_URL","value":"${SITE_URL}","type":"PLAINTEXT"},
     {"name":"SMOKE_CLIENT","value":"${CLIENT}","type":"PLAINTEXT"},
     {"name":"CONVEX_ADMIN_KEY","value":"${ADMIN_ARN}","type":"SECRETS_MANAGER"}]},
 "vpcConfig":{"vpcId":"${VPC_ID}","subnets":${SUBNETS_JSON},"securityGroupIds":["${SG_ID}"]},
 "serviceRole":"arn:aws:iam::${ACCT}:role/${ROLE}"}
JSON
)
if aws codebuild batch-get-projects --names "$PROJECT_NAME" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$PROJECT_NAME"; then
  aws codebuild update-project --cli-input-json "$cfg" >/dev/null; else aws codebuild create-project --cli-input-json "$cfg" >/dev/null; fi

# build the combined bundle: ./neural-ops + ./mempalace (with node_modules)
log "bundling neural-ops + mempalace (+node_modules) — this is ~140M, a moment…"
B=/tmp/spine-bundle; rm -rf "$B"; mkdir -p "$B/neural-ops" "$B/mempalace"
( cd "$REPO_ROOT" && tar cf - --exclude='.git' --exclude='.terraform' --exclude='*.tfstate*' --exclude='.env' tools runtime frontdoor acp nrt agents requirements.txt 2>/dev/null ) | ( cd "$B/neural-ops" && tar xf - )
( cd "$MEMPALACE_DIR" && tar cf - --exclude='.git' --exclude='.env' --exclude='*.env*' . 2>/dev/null ) | ( cd "$B/mempalace" && tar xf - )
# -y PRESERVES symlinks (node_modules/.bin/convex is a symlink; following it breaks the CLI's relative paths)
zip="/tmp/spine-bundle.zip"; ( cd "$B" && rm -f "$zip" && zip -qyr "$zip" . )
KEY="src/spine-verify.zip"; aws s3 cp "$zip" "s3://${BUCKET}/${KEY}" >/dev/null
log "bundle uploaded ($(du -h "$zip" | cut -f1))"

bid=$(aws codebuild start-build --project-name "$PROJECT_NAME" \
      --source-location-override "${BUCKET}/${KEY}" --source-type-override S3 \
      --buildspec-override "$(cat "$HERE/buildspec-spine-verify.yml")" \
      --query 'build.id' --output text)
log "build $bid — polling…"
while :; do st=$(aws codebuild batch-get-builds --ids "$bid" --query 'builds[0].buildStatus' --output text); [ "$st" = IN_PROGRESS ] && sleep 12 || break; done
log "status: $st"
echo "$bid" > /tmp/spine-verify-build.txt
S=$(echo "$bid" | cut -d: -f2)
aws logs get-log-events --log-group-name "/aws/codebuild/${PROJECT_NAME}" --log-stream-name "$S" --query 'events[*].message' --output text 2>&1 | grep -vE '^\s*\[Container\]' | tail -45
[ "$st" = SUCCEEDED ]
