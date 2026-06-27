#!/usr/bin/env bash
# Live embedder proof — set GEMINI_API_KEY in the Convex env, deploy the Gemini-embedder functions, and
# prove ranked semantic retrieval, all on a VPC-attached CodeBuild (Convex is internal). Run after the
# spine is up + the gemini-embedder branch is the local Mempalace state. Usage: ./embedder-verify.sh
set -euo pipefail
REGION="${REGION:-ap-south-1}"; ENVIRONMENT="${ENVIRONMENT:-dogfood}"; PROJECT="${PROJECT:-neos}"
NAME="${PROJECT}-${ENVIRONMENT}"; CLIENT="${SMOKE_CLIENT:-neuraledge}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$(cd "$HERE/../terraform" && pwd)"; REPO_ROOT="$(cd "$HERE/../.." && pwd)"
MEMPALACE_DIR="${MEMPALACE_DIR:-$REPO_ROOT/../Mempalace_NEOS}"
ACCT="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${NAME}-codebuild-src-${ACCT}"; ROLE="${NAME}-codebuild-role"; PROJECT_NAME="${NAME}-embedder-verify"
log(){ printf '\033[1;33m[embedder-verify]\033[0m %s\n' "$*"; }
tfout(){ ( cd "$TF_DIR" && terraform output -raw "$1" ); }
tfjson(){ ( cd "$TF_DIR" && terraform output -json "$1" ); }

VPC_ID="$(tfout vpc_id)"; API_URL="$(tfout convex_api_url)"; SITE_URL="$(tfout convex_site_url)"
ADMIN_ARN="$(tfjson secret_arns | python3 -c 'import json,sys;print(json.load(sys.stdin)["CONVEX_SELF_HOSTED_ADMIN_KEY"])')"
BR_ARN="$(aws secretsmanager describe-secret --secret-id ${NAME}/AWS_BEARER_TOKEN_BEDROCK --query ARN --output text)"
SUBNETS="$(tfjson private_subnet_ids | python3 -c 'import json,sys;print(",".join(json.load(sys.stdin)))')"
SG_ID="$(aws ec2 describe-security-groups --filters Name=group-name,Values="${NAME}-codebuild-sg" Name=vpc-id,Values="$VPC_ID" --query 'SecurityGroups[0].GroupId' --output text)"
log "VPC=$VPC_ID API=$API_URL SG=$SG_ID"

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
     {"name":"CONVEX_ADMIN_KEY","value":"${ADMIN_ARN}","type":"SECRETS_MANAGER"},
     {"name":"AWS_BEARER_TOKEN_BEDROCK","value":"${BR_ARN}","type":"SECRETS_MANAGER"}]},
 "vpcConfig":{"vpcId":"${VPC_ID}","subnets":${SUBNETS_JSON},"securityGroupIds":["${SG_ID}"]},
 "serviceRole":"arn:aws:iam::${ACCT}:role/${ROLE}"}
JSON
)
if aws codebuild batch-get-projects --names "$PROJECT_NAME" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$PROJECT_NAME"; then
  aws codebuild update-project --cli-input-json "$cfg" >/dev/null; else aws codebuild create-project --cli-input-json "$cfg" >/dev/null; fi

log "bundling neural-ops + mempalace (+node_modules, symlinks preserved)…"
B=/tmp/embedder-bundle; rm -rf "$B"; mkdir -p "$B/neural-ops" "$B/mempalace"
( cd "$REPO_ROOT" && tar cf - --exclude='.git' --exclude='.terraform' --exclude='*.tfstate*' --exclude='.env' tools runtime frontdoor acp nrt agents requirements.txt 2>/dev/null ) | ( cd "$B/neural-ops" && tar xf - )
( cd "$MEMPALACE_DIR" && tar cf - --exclude='.git' --exclude='.env' --exclude='*.env*' . 2>/dev/null ) | ( cd "$B/mempalace" && tar xf - )
zip="/tmp/embedder-bundle.zip"; ( cd "$B" && rm -f "$zip" && zip -qyr "$zip" . )
KEY="src/embedder-verify.zip"; aws s3 cp "$zip" "s3://${BUCKET}/${KEY}" >/dev/null
log "bundle uploaded ($(du -h "$zip" | cut -f1))"

bid=$(aws codebuild start-build --project-name "$PROJECT_NAME" \
      --source-location-override "${BUCKET}/${KEY}" --source-type-override S3 \
      --buildspec-override "$(cat "$HERE/buildspec-embedder-verify.yml")" \
      --query 'build.id' --output text)
log "build $bid — polling…"
while :; do st=$(aws codebuild batch-get-builds --ids "$bid" --query 'builds[0].buildStatus' --output text); [ "$st" = IN_PROGRESS ] && sleep 12 || break; done
log "status: $st"
S=$(echo "$bid" | cut -d: -f2)
aws logs get-log-events --log-group-name "/aws/codebuild/${PROJECT_NAME}" --log-stream-name "$S" --query 'events[*].message' --output text 2>&1 | grep -vE '^\s*\[Container\]' | tail -40
[ "$st" = SUCCEEDED ]
