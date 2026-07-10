#!/usr/bin/env bash
# nc-web deploy — build the static SPA and (re)start the Traefik-fronted container on the matrix box.
#
# The box runs mdad = Traefik v3 (NOT nginx). nc-web is a small static container on the `traefik` network
# with Host(`chat.neuraledge.in`) labels, same pattern as the Element client; Traefik auto-provisions TLS
# via its "default" (Let's Encrypt) resolver once chat.neuraledge.in publicly resolves to the box.
# No secrets here. Box access: durable key or EC2 Instance Connect (see OPS-ACCESS.md).
#
# Usage:
#   BOX_HOST=ubuntu@13.201.114.109 SSH_KEY=~/.ssh/box_key ./nc-web/deploy/deploy.sh
# Optional: VITE_MATRIX_BASE_URL=https://matrix.neuraledge.in (baked into the build), REMOTE_DIR
set -euo pipefail
cd "$(dirname "$0")/.."

: "${BOX_HOST:?set BOX_HOST=ubuntu@<box-ip>}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/box_key}"
REMOTE_DIR="${REMOTE_DIR:-/home/ubuntu/nc-web}"
SSH=(ssh -o StrictHostKeyChecking=accept-new -i "$SSH_KEY")

echo "==> build"
npm ci
npm run build   # tsc --noEmit && vite build -> dist/

echo "==> sync dist/ + compose + conf -> $BOX_HOST:$REMOTE_DIR"
"${SSH[@]}" "$BOX_HOST" "mkdir -p $REMOTE_DIR/html"
rsync -az --delete -e "${SSH[*]}" dist/ "$BOX_HOST:$REMOTE_DIR/html/"
rsync -az -e "${SSH[*]}" deploy/docker-compose.yml deploy/container-default.conf "$BOX_HOST:$REMOTE_DIR/"

echo "==> (re)start the Traefik-fronted container"
"${SSH[@]}" "$BOX_HOST" "cd $REMOTE_DIR && (docker compose up -d --force-recreate || docker restart nc-web) && docker ps --filter name=nc-web --format '{{.Names}} {{.Status}}'"

echo "==> deployed. Once chat.neuraledge.in resolves to the box, verify: https://chat.neuraledge.in"
