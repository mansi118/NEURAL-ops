#!/usr/bin/env bash
# NEOS image build — no local Docker required. Builds the runtime + bridge images on AWS CodeBuild
# from an S3 source zip and pushes to ECR. Idempotent; safe to re-run.
#
# Usage (creds in env or .env mapped by the caller):
#   ./build.sh bootstrap          # ECR repos (via terraform -target) + S3 bucket + CodeBuild role/project
#   ./build.sh runtime            # build+push neos-<env>-runtime  (context = repo root)
#   ./build.sh bridge             # build+push neos-<env>-bridge   (context = ../Mempalace_NEOS/services)
#   ./build.sh runtime bridge     # both
#
# Env knobs: REGION (ap-south-1) · ENVIRONMENT (dogfood) · MEMPALACE_DIR (../../../Mempalace_NEOS)
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
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
BUCKET="${NAME}-codebuild-src-${ACCOUNT_ID}"
ROLE="${NAME}-codebuild-role"
PROJECT_NAME="${NAME}-image-build"
GITSHA="$(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo manual)"

log() { printf '\033[1;36m[build]\033[0m %s\n' "$*"; }

bootstrap() {
  log "ECR repos via terraform -target (kept in state)"
  ( cd "$TF_DIR" && terraform apply -input=false -auto-approve \
      -target=aws_ecr_repository.runtime -target=aws_ecr_repository.bridge )

  log "S3 source bucket: $BUCKET"
  if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
    aws s3api put-bucket-encryption --bucket "$BUCKET" \
      --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
    aws s3api put-public-access-block --bucket "$BUCKET" \
      --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  fi

  log "CodeBuild IAM role: $ROLE"
  local trust='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"codebuild.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
  aws iam get-role --role-name "$ROLE" >/dev/null 2>&1 || \
    aws iam create-role --role-name "$ROLE" --assume-role-policy-document "$trust" >/dev/null
  local policy
  policy=$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"],"Resource":"*"},
 {"Effect":"Allow","Action":["s3:GetObject","s3:GetObjectVersion","s3:PutObject"],"Resource":"arn:aws:s3:::${BUCKET}/*"},
 {"Effect":"Allow","Action":["ecr:GetAuthorizationToken"],"Resource":"*"},
 {"Effect":"Allow","Action":["ecr:BatchCheckLayerAvailability","ecr:InitiateLayerUpload","ecr:UploadLayerPart","ecr:CompleteLayerUpload","ecr:PutImage","ecr:BatchGetImage","ecr:DescribeImages"],"Resource":"arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${NAME}-*"}
]}
JSON
)
  aws iam put-role-policy --role-name "$ROLE" --policy-name "${NAME}-codebuild-policy" --policy-document "$policy"
  sleep 8  # IAM propagation

  log "CodeBuild project: $PROJECT_NAME (privileged; non-VPC — images push via the public ECR endpoint)"
  local cfg
  cfg=$(cat <<JSON
{"name":"${PROJECT_NAME}",
 "source":{"type":"S3","location":"${BUCKET}/placeholder.zip","buildspec":"infra/build/buildspec-image.yml"},
 "artifacts":{"type":"NO_ARTIFACTS"},
 "environment":{"type":"LINUX_CONTAINER","image":"aws/codebuild/standard:7.0","computeType":"BUILD_GENERAL1_SMALL","privilegedMode":true,
   "environmentVariables":[{"name":"AWS_DEFAULT_REGION","value":"${REGION}"}]},
 "serviceRole":"arn:aws:iam::${ACCOUNT_ID}:role/${ROLE}"}
JSON
)
  if aws codebuild batch-get-projects --names "$PROJECT_NAME" --query 'projects[0].name' --output text 2>/dev/null | grep -q "$PROJECT_NAME"; then
    aws codebuild update-project --cli-input-json "$cfg" >/dev/null
  else
    aws codebuild create-project --cli-input-json "$cfg" >/dev/null
  fi
  log "bootstrap done."
}

# build_one <name> <ecr-repo-suffix> <context-dir> <dockerfile-rel-to-context>
build_one() {
  local label="$1" repo_suffix="$2" ctx="$3" dockerfile="$4"
  local repo="${REGISTRY}/${repo_suffix}"
  local key="src/${label}-${GITSHA}.zip" zip="/tmp/${label}-src.zip"
  log "zipping context $ctx → $zip"
  # SECURITY: never ship secrets/state to S3. Exclude .env*, tfvars, tfstate, .terraform, vcs, deps.
  ( cd "$ctx" && rm -f "$zip" && zip -qr "$zip" . \
      -x '*.git*' 'node_modules/*' '*.terraform/*' '*.terraform' \
         '.env' '.env.*' '*.env' \
         '*.tfvars' '*.tfstate' '*.tfstate.*' '*.tfplan' 'tf.plan' )
  # Precise: real secret-bearing files only (.env*, terraform.tfvars, *.tfstate) — not files merely
  # NAMED "secret"/"*.tfvars.example". Anchored on $ = filename end in `unzip -l` output.
  if unzip -l "$zip" | grep -iE '(^|/)\.env(\.[^/]*)?$|(^|/)[^/]*\.tfvars$|\.tfstate([0-9.]*)?$' ; then
    log "ABORT: real secret/state file present in zip"; return 1
  fi
  log "  zip clean (no .env / tfvars / tfstate)"
  aws s3 cp "$zip" "s3://${BUCKET}/${key}" >/dev/null
  log "starting CodeBuild for $label ($repo:$GITSHA)"
  local bid
  bid=$(aws codebuild start-build --project-name "$PROJECT_NAME" \
        --source-location-override "${BUCKET}/${key}" --source-type-override S3 \
        --buildspec-override "$(cat "$HERE/buildspec-image.yml")" \
        --environment-variables-override \
          name=ECR_REPO,value="$repo",type=PLAINTEXT \
          name=IMAGE_TAG,value="$GITSHA",type=PLAINTEXT \
          name=DOCKERFILE,value="$dockerfile",type=PLAINTEXT \
          name=BUILD_CONTEXT,value=".",type=PLAINTEXT \
        --query 'build.id' --output text)
  log "build id $bid — polling…"
  while :; do
    local st
    st=$(aws codebuild batch-get-builds --ids "$bid" --query 'builds[0].buildStatus' --output text)
    case "$st" in
      SUCCEEDED) log "$label SUCCEEDED → ${repo}:${GITSHA}"; break ;;
      IN_PROGRESS) sleep 12 ;;
      *) log "$label build $st — see CodeBuild logs for $bid"; return 1 ;;
    esac
  done
}

cmd="${1:-}"; [ -n "$cmd" ] || { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 1; }
for arg in "$@"; do
  case "$arg" in
    bootstrap) bootstrap ;;
    runtime)   build_one runtime "${NAME}-runtime" "$REPO_ROOT" "./Dockerfile" ;;
    bridge)    build_one bridge  "${NAME}-bridge"  "$MEMPALACE_DIR/services" "./Dockerfile" ;;
  esac
done
