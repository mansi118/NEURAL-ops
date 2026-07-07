# nc-channels placement — cross-VPC design (Track B1)

> Resolves the one offline blocker before the Matrix box window. The held `nc-channels.tf` was written for
> the **Fargate Synapse in the spine VPC** — now disarmed (#78). The real homeserver is the **EC2
> `matrix-server` in the default VPC (`172.31`)**, so the placement + the held TF must be re-targeted.

## The constraint
`nc-channels` runs `frontdoor.orchestrator.handle → dispatch` **in-process** (not a thin transport), so it needs:
1. **Receive** AS transactions FROM Synapse (`matrix.neuraledge.in`, default VPC `172.31`, public on 443/8448).
2. **Reach** the palace `/mcp` (`convex.neos-dogfood.local:3211`, spine VPC `10.40`, **internal only**).
3. **Send** CS-API replies TO Synapse (public `matrix.neuraledge.in`).

The two networks: default VPC `172.31/16` (Synapse + unrelated workloads) · spine VPC `10.40/16` (palace/runtime).

## The fork
- **Option A — on the `matrix-server` box (default VPC):** Synapse hop = localhost; but the **palace hop needs
  default↔spine reach** (VPC peering or a public palace endpoint — none exists), AND it runs the NEOS runtime
  in-process **on the Matrix box** (couples runtime execution + palace creds onto a box with unrelated
  workloads). ✗ Rejected: peers a messy multi-workload default VPC into the spine, and mislocates the runtime.
- **Option B — in the spine VPC (recommended):** palace hop = **internal** (trivial). Synapse is **public**, so
  the reply hop is plain egress to `matrix.neuraledge.in` — **no peering**. The only thing to solve is the
  **inbound** (Synapse must reach nc-channels' `/_matrix/app/v1/transactions`).

## Decision — Option B: nc-channels in the spine VPC, HS-reachable via a public HTTPS endpoint
The Matrix AS pattern *requires* the HS to reach the AS `url`. Since the HS is public, the AS endpoint must be
HS-reachable — the standard pattern is a **small public HTTPS ALB → nc-channels' AS port**, and the endpoint
is **authenticated** (`verify_hs_token`, constant-time — `service.py:68`), so public exposure is bounded to a
token-gated `/transactions` route. This avoids peering the unrelated-workload default VPC into the spine.

**Topology:**
```
Synapse (EC2, default VPC, public) ──PUT /transactions (Bearer hs_token)──► public ALB ──► nc-channels (spine VPC, private)
nc-channels ──reply_send CS-API (Bearer as_token)──► https://matrix.neuraledge.in  (public egress)
nc-channels ──/mcp──► convex.neos-dogfood.local:3211  (spine VPC internal)
```

## What the held `nc-channels.tf` needs re-targeted (do NOT apply as-is)
Current (spine-Fargate-Synapse assumptions) → corrected (EC2/public-Synapse):
- **Ingress SG** `security_groups = [aws_security_group.synapse[0].id]` → **from the ALB SG** (the Fargate
  Synapse SG no longer exists; that reference now errors). The public ALB fronts the AS port.
- **Add** a public HTTPS ALB + ACM cert for the AS `url` (e.g. `nc-channels.neuraledge.in` or an ALB DNS),
  target group → nc-channels; the AS `registration.yaml` `url` = that public HTTPS endpoint.
- **`enable_comms_tier` coupling** — the held TF requires the comms tier for the Synapse SG; that coupling is
  now moot. Re-gate `nc-channels.tf` purely on `enable_nc_channels`, independent of the (unused) Fargate Synapse.
- **Egress** already correct (all TLS out → reaches public Synapse + palace).
- **Secrets/env** unchanged (AS_TOKEN/HS_TOKEN/ADAPTER_HMAC + runtime creds for in-process dispatch).

## The box sequence for Bar 1 (with the above placement)
1. `[ML]` **AS-registration** on `matrix-server` per #79 — the `url` in the registration = the public ALB
   endpoint (below). Backup → additive edit → restart → verify → rollback known first.
2. `[A]` **Re-target `nc-channels.tf`** (the SG + ALB changes above) — authored, HELD (`enable_nc_channels=false`)
   until 3.
3. `[BOX]` **Build `serve()`/`_cs_api_call`** against real `matrix.neuraledge.in`, hand-driven first.
4. `[ML]` **Deploy** — stand up the ALB + flip `enable_nc_channels=true`.
5. `[LIVE]` `@neos-bot` + seat + room → Element → **round-trip = Bar 1**.

## Open sub-decision for the box
The public AS endpoint needs a DNS name + ACM cert. Simplest: an ALB with its AWS DNS + a cert on a
`nc-channels.neuraledge.in` record (you own the zone — `matrix.neuraledge.in` proves it). Alternatively, if
you'd rather not expose the AS publicly at all, the fallback is **VPC peering** default↔spine scoped by SG
(Synapse SG → nc-channels port only) — more locked-down but couples the two VPCs. Recommendation stands:
public token-gated ALB unless you want the peering lockdown.
