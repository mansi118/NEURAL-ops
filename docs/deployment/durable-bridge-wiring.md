# Durable bridge→wrapper wiring (Bar-2 loose-end (b)) — AS BUILT 2026-07-09

**Problem.** Bar 2 shipped the Matrix→spine connection with `SEAT_URL` pinned to the wrapper's **dynamic**
ECS task IP (`10.40.53.174`). It worked only because the task hadn't been replaced; any wrapper redeploy →
new IP → dead wire. (The bridge process itself was already durable — it runs as a Docker container
`nc-channels-bar1a`, `restart=unless-stopped`, on the matrix box's `matrix-homeserver` network; code
bind-mounted from `/home/ubuntu/neural-ops`. So process supervision was NOT the gap; the IP pin was.)

**Fix.** The wrapper is Cloud-Map registered as `seat-wrapper.neos-dogfood.local` (`wrapper.tf`), whose A
record auto-follows the ECS task on redeploy. Make that name resolvable from the matrix box and point the
bridge at it. Three parts:

## 1 — Spine: associate the Cloud Map zone with the matrix VPC (terraform)
`peering.tf` → `aws_route53_zone_association.matrix_wrapper_discovery` (gated on `enable_matrix_peering`).
Additive, reversible, **0-destroy** (`terraform plan -var-file=bar2-live.tfvars` = `1 to add, 0 change, 0
destroy`). Applied 2026-07-09; the zone `Z07885953C93W0YGKFUNQ` now lists both the spine and matrix VPCs.

## 2 — Box: teach systemd-resolved to resolve the `.local` Cloud Map zone
**This is the non-obvious prerequisite.** systemd-resolved treats `.local` as mDNS and won't forward it to
the VPC resolver — so the name fails via `getent`/the container even though the zone is correct. Install the
routing-only drop-in (`resolved-neos-cloudmap.conf`) → `/etc/systemd/resolved.conf.d/` and restart
systemd-resolved. Verified: `seat-wrapper.neos-dogfood.local` resolves system-wide; `neuraledge.in` and
Synapse federation unaffected. Docker's embedded DNS (`127.0.0.11`) forwards through the host, so the
**container inherits this fix automatically** — no per-container `--dns` needed.

## 3 — Box: repoint the bridge container's SEAT_URL at the stable name
Recreate `nc-channels-bar1a` with only `SEAT_URL` changed (everything else byte-identical), keeping
`--restart unless-stopped`:
```
CID=nc-channels-bar1a
sudo docker inspect $CID --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^(AS_TOKEN|HS_TOKEN|AS_URL|AS_USER_REGEX|AS_SENDER|AS_SERVER_NAME|AS_TENANT|HS_BASE_URL|LISTEN_HOST|LISTEN_PORT|SEAT_URL|FORWARD_TOKEN|PYTHONPATH)=' \
  | sudo tee /home/ubuntu/nc-channels-bar1a.env >/dev/null
sudo sed -i 's#^SEAT_URL=.*#SEAT_URL=http://seat-wrapper.neos-dogfood.local:8090/seat/turn#' /home/ubuntu/nc-channels-bar1a.env
sudo chmod 600 /home/ubuntu/nc-channels-bar1a.env
sudo docker stop $CID && sudo docker rename $CID ${CID}-preDNS      # rollback kept
sudo docker run -d --name $CID --network matrix-homeserver --restart unless-stopped \
  -w /app -v /home/ubuntu/neural-ops:/app --env-file /home/ubuntu/nc-channels-bar1a.env \
  python:3.12-slim sh -c "pip install -q pyyaml >/dev/null 2>&1 && python3 tools/run_nc_channels_seat.py"
```
See `nc-channels-bar1a.env.example` for the variable set.

## Durability proof (executed 2026-07-09)
Forced a wrapper redeploy (`aws ecs update-service --force-new-deployment`): task IP moved
`10.40.53.174 → 10.40.36.208`, Cloud Map converged to the new IP, and the bridge container resolved +
reached the new IP (L7 403 auth-gate) with **zero config change**. That is the wire proven redeploy-durable.

## Rollback
`sudo docker stop nc-channels-bar1a && sudo docker rename nc-channels-bar1a-preDNS nc-channels-bar1a && sudo docker start nc-channels-bar1a`
(then delete the resolved drop-in if reverting DNS). The pre-DNS container is retained stopped as the rollback.
