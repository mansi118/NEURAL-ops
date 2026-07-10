# nc-web launch runbook — chat.neuraledge.in

nc-web is a pure Matrix client (no backend). The matrix box runs **mdad = Traefik v3** (NOT nginx), so
nc-web is served as a small static container on the box's existing `traefik` network, routed by Host —
the same pattern as the Element client. This is additive: it touches no mdad service.

## Status (2026-07-10) — box side DONE, one DNS step remains

Already deployed and verified on the box (`i-0dcfbf5e0eecb4dcd`, `13.201.114.109`):
- Container `nc-web` (nginx:alpine) serving the built SPA from `/home/ubuntu/nc-web/html`, on the `traefik`
  network, labels `Host(chat.neuraledge.in)` · entrypoint `web-secure` · `tls.certResolver=default`.
- Verified: container serves HTTP 200; Traefik routes the Host (80 → 308 → HTTPS); local HTTPS via Traefik
  returns 200. TLS will auto-provision (Let's Encrypt) the moment the public DNS points at the box.

## THE one remaining step — DNS at the registrar `[you]`

`neuraledge.in` is authoritative on **ns1/ns2.dns-parking.com (Hostinger)** — NOT Route53. (There is a
Route53 zone `Z0391056MP6NRW9P2EWI` with a mirror `chat A` record, but it is INERT because the domain does
not delegate to it.) `element`/`matrix` work because they have explicit A records at Hostinger; `chat` falls
through the wildcard `*.neuraledge.in → CloudFront`, so it must get its own record there:

1. Hostinger hPanel → Domains → `neuraledge.in` → DNS / Nameservers.
2. Add record: **Type `A`, Name `chat`, Value `13.201.114.109`, TTL `300`** (identical to the existing
   `element` / `matrix` A records).
3. Wait for propagation (≤5 min). Traefik then completes the ACME HTTP-01 challenge and issues the cert
   automatically (if it doesn't within a few minutes, nudge it: `docker restart nc-web` on the box).

Verify: open **https://chat.neuraledge.in** → NeuralChat login. Sign in with a seat account and chat with
Aria / Recon. That is the MVP launch — branded product chat replacing Element, needing none of the gated
backend deploys.

## Redeploy a new build (agent-drivable)
```
BOX_HOST=ubuntu@13.201.114.109 SSH_KEY=~/.ssh/box_key ./nc-web/deploy/deploy.sh
```
Builds, rsyncs `dist/` to `/home/ubuntu/nc-web/html`, and recreates the container from
`nc-web/deploy/docker-compose.yml`.

## Progressive enhancement (as producer harnesses go live)
- Fidelity dashboard fills when the fidelity harness publishes `m.neop.fidelity` to the ops room.
- Decision Queue fills when the flywheel/vault/governance emit sinks post `m.neop.proposal`; approve/reject
  writes `m.neop.verdict` back. These need the harnesses' live seams (Convex/Nova) + a schedule — the
  prod-gated deploys in `technical-plan-3-month-2026-07.md`.

## Rollback
`docker rm -f nc-web` on the box removes the site with zero effect on any mdad service; delete the Hostinger
`chat` record to revert DNS. nc-web holds no server state.
