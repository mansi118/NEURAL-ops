# nc-web launch runbook — chat.neuraledge.in

The offline build of nc-web is complete and CI-green (PR-A…PR-E). This is the ONE gated step: hosting
it. It mirrors the existing `element.neuraledge.in` vhost on the matrix box — nc-web is a pure Matrix
client, so there is no backend to deploy; it just needs static hosting pointed at the live homeserver.

Owner: `[you]` — DNS + TLS + the box's nginx are prod/box actions. The agent can drive `deploy/deploy.sh`
(the build+sync) once the box vhost + cert exist, but the one-time setup below is yours.

## Prerequisites
- Box access: durable key `~/.ssh/box_key` or EC2 Instance Connect (see `OPS-ACCESS.md`). Box = the mdad
  matrix EC2 (`i-0dcfbf5e0eecb4dcd`, `13.201.114.109`) that already serves `matrix.` + `element.`.
- The homeserver `matrix.neuraledge.in` is live (it is).

## One-time setup (yours)
1. DNS — add an A record `chat.neuraledge.in` → the matrix box's public IP (same target as `element.`).
2. Install the vhost:
   - `sudo cp nc-web/deploy/nginx-chat.neuraledge.in.conf /etc/nginx/sites-available/chat.neuraledge.in`
   - `sudo ln -s /etc/nginx/sites-available/chat.neuraledge.in /etc/nginx/sites-enabled/`
   - `sudo mkdir -p /var/www/nc-web`
3. TLS — `sudo certbot --nginx -d chat.neuraledge.in` (certbot rewrites the 80→443 redirect + ssl_* lines,
   same as the other vhosts).
4. `sudo nginx -t && sudo systemctl reload nginx`.

## Deploy the build (repeatable; agent-drivable once step 1–4 exist)
```
BOX_HOST=ubuntu@13.201.114.109 SSH_KEY=~/.ssh/box_key ./nc-web/deploy/deploy.sh
```
It runs `npm ci && npm run build`, rsyncs `dist/` to `/var/www/nc-web` atomically, and reloads nginx.

## First-contact verification (the MVP launch)
1. Open `https://chat.neuraledge.in`.
2. Sign in with a seat account (e.g. the `@yatharth_client` / `@mansi-neop` credentials).
3. Chat with Aria / Recon in their rooms — this is branded product chat replacing Element, needing NONE
   of the gated backend deploys.

## Progressive enhancement (as each producer harness goes live)
- Fidelity dashboard fills when the fidelity harness publishes `m.neop.fidelity` snapshots to the ops room.
- Decision Queue fills when the flywheel/vault/governance emit sinks post `m.neop.proposal` events, and
  approve/reject writes `m.neop.verdict` back. These need the harnesses' live seams (Convex/Nova) + a
  schedule — the same prod-gated deploys tracked in `technical-plan-3-month-2026-07.md`.

## Rollback
`dist/` is a static bundle; keep the previous one (`/var/www/nc-web.bak`) and swap back + reload nginx.
No data migration — nc-web holds no server state.
