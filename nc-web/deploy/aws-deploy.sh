#!/usr/bin/env bash
# nc-web AWS-native deploy: build -> S3 sync -> CloudFront invalidation.
#
# Hosting is 100% AWS and ISOLATED from the matrix/spine box (which we do not touch): a private S3
# bucket fronted by a CloudFront distribution (OAC, HTTPS via the default *.cloudfront.net cert, SPA
# error routing 403/404 -> /index.html). The client still talks to the public Matrix homeserver
# (matrix.neuraledge.in, itself on EC2). No secrets here.
#
# Provisioned resources (ap-south-1 / acct 071126865245):
#   S3 bucket : neuralchat-web-071126865245   (private, default BPA)
#   CloudFront: ESZ2GZFNY5Z8U  ->  https://d1fpr59vpk40a3.cloudfront.net
#   OAC       : E18QDL446BAGGI
#
# Usage:  ./nc-web/deploy/aws-deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

BUCKET="${BUCKET:-neuralchat-web-071126865245}"
DIST_ID="${DIST_ID:-ESZ2GZFNY5Z8U}"
REGION="${AWS_REGION:-ap-south-1}"

echo "==> build"
npm ci
npm run build   # tsc --noEmit && vite build -> dist/

echo "==> sync dist/ -> s3://$BUCKET (immutable assets, no-cache index.html)"
aws s3 sync dist/assets/ "s3://$BUCKET/assets/" --delete --region "$REGION" \
  --cache-control "public,max-age=31536000,immutable"
aws s3 cp dist/index.html "s3://$BUCKET/index.html" --region "$REGION" \
  --cache-control "no-cache"

echo "==> invalidate CloudFront $DIST_ID"
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*" \
  --query "Invalidation.Status" --output text

echo "==> live: https://d1fpr59vpk40a3.cloudfront.net"
