#!/usr/bin/env bash
# nc-web deploy — build the static SPA and sync it to the matrix box's nginx docroot.
#
# No secrets in here. Box access is via the durable key or EC2 Instance Connect (see OPS-ACCESS.md).
# This is the executable half of the gated launch step; the one-time box setup (DNS, TLS, enabling the
# vhost) is in docs/deployment/nc-web-deploy-runbook.md.
#
# Usage:
#   BOX_HOST=ubuntu@13.201.114.109  SSH_KEY=~/.ssh/box_key  ./deploy/deploy.sh
# Optional:
#   VITE_MATRIX_BASE_URL=https://matrix.neuraledge.in  (baked into the build; defaults to that)
#   REMOTE_DOCROOT=/var/www/nc-web
set -euo pipefail

cd "$(dirname "$0")/.."

: "${BOX_HOST:?set BOX_HOST=ubuntu@<box-ip>}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/box_key}"
REMOTE_DOCROOT="${REMOTE_DOCROOT:-/var/www/nc-web}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -i "$SSH_KEY")

echo "==> build"
npm ci
npm run build   # tsc --noEmit && vite build -> dist/

echo "==> sync dist/ -> $BOX_HOST:$REMOTE_DOCROOT (atomic via a temp dir + mv)"
TMP="/tmp/nc-web-$(date +%s 2>/dev/null || echo deploy)"
rsync -az --delete -e "ssh ${SSH_OPTS[*]}" dist/ "$BOX_HOST:$TMP/"
ssh "${SSH_OPTS[@]}" "$BOX_HOST" \
  "sudo mkdir -p $REMOTE_DOCROOT && sudo rsync -a --delete $TMP/ $REMOTE_DOCROOT/ && rm -rf $TMP && sudo nginx -t && sudo systemctl reload nginx"

echo "==> deployed. Verify: https://chat.neuraledge.in"
