# Track B1 — `nc-channels` cross-VPC placement design

> The last architecture decision before Bar 1. `nc-channels` runs the orchestrator **in-process**
> (`frontdoor/orchestrator.py` → `runtime.core.dispatch`), so wherever it lives it must reach whatever that
> dispatch needs. This doc names the two options, their real networking costs, the no-NAT + cross-VPC
> constraints, and a recommendation. Offline design — no gate. Companion to `ADR-matrix-homeserver` (why the
> EC2 Synapse), `nc-channels-transport-deploy-design.md` (D2), and the held `infra/terraform/nc-channels.tf`.

## The constraint (two endpoints in two different VPCs)
- **Synapse** = the EC2 `matrix-server` box, **default VPC `172.31/16`**, private IP `172.31.42.0`, public
  `matrix.neuraledge.in` (:8008 client / :8448 fed). `nc-channels` needs it **both ways**: HS→AS transaction
  PUTs (Synapse → nc-channels) and AS→HS `reply_send` (nc-channels → Synapse CS-API).
- **Palace `/mcp`** = `convex.neos-dogfood.local:3211`, **spine VPC `10.40/16`**, internal (Cloud Map, no
  public endpoint). Needed by the in-process dispatch — **but only for memory (Bar 2)**.
- **The spine VPC is no-NAT** (`enable_nat_gateway=false`) → its private subnets have **no public-internet
  egress**. So a spine-VPC `nc-channels` **cannot reach public `matrix.neuraledge.in`** without either a NAT
  gateway or a private route (VPC peering to the EC2 box's private IP). This is why the held TF's
  `egress 0.0.0.0/0 → "Synapse CS-API"` is broken for the real Synapse.

## The Bar-1 shortcut (register this before choosing): **echo needs NO palace**
Bar 1 is the **echo** NEop, which **does not query memory** — its dispatch makes no `/mcp` call. So for Bar 1,
`nc-channels` needs **only the Synapse hop**, not the palace hop. The cross-VPC palace problem is entirely a
**Bar-2** concern. That means a fast first-contact is possible without any peering — but at the cost of a
placement you'd revisit for Bar 2. Name the trade explicitly rather than defaulting into it.

## Option A — `nc-channels` ON the `matrix-server` EC2 box (default VPC)
- **Synapse hop:** localhost (HS→AS to `localhost:8010`; AS→HS to `localhost:8008`). Trivial, no exposure.
- **Palace hop (Bar 2 only):** default-VPC → spine-VPC internal Cloud Map — needs **VPC peering** + the spine
  private hosted zone associated with the default VPC (so `convex.neos-dogfood.local` resolves there).
- **Costs:** runs the in-process runtime (LLM/palace creds) on the **production Synapse box** — couples
  `nc-channels`'s failure/compromise domain to the homeserver, the opposite of **D2** (own failure domain).
  Managing a service by hand on that box (you keep SSH locked) is friction.
- **Good for:** a fast Bar-1 echo smoke (localhost Synapse, no palace, no peering). **Throwaway for Bar 2.**

## Option B — `nc-channels` IN the spine VPC (`10.40`) — what the held TF *location* assumes
- **Palace hop:** internal, trivial (same VPC). ✓ (the hop that matters for Bar 2).
- **Synapse hop:** needs to reach the EC2 Synapse (default VPC). Two sub-choices:
  - **Via VPC peering to the EC2 box's PRIVATE IP** (`172.31.42.0:8008`) — private routing, **no NAT needed**,
    no public exposure. Synapse→nc-channels (AS PUT) also rides peering to nc-channels' private IP. **This is
    the clean path** and sidesteps the no-NAT problem entirely.
  - (Reaching public `matrix.neuraledge.in` from the no-NAT spine VPC would need a NAT gateway — avoid;
    peering-to-private-IP is strictly better.)
- **Costs:** VPC peering (default↔spine) + routes + SGs both directions + the AS registration `url` must be a
  peering-reachable endpoint (nc-channels' spine-VPC private IP, or an internal NLB — not the Cloud Map name,
  which the default VPC won't resolve unless the hosted zone is shared).
- **Good for:** **both Bar 1 and Bar 2 on the same footing.** Keeps `nc-channels` off both the runtime *and*
  the Synapse box (D2-compliant). This is the durable placement.

## The held `nc-channels.tf` — what re-targeting means (either option)
It's currently written for an in-spine-VPC Fargate Synapse (retired). To match reality:
- **SG ingress:** `security_groups = [aws_security_group.synapse[0].id]` → **gone** (that SG no longer
  exists). Replace with ingress from the **peering CIDR / the EC2 Synapse's SG across the peer**, on
  `nc_channels_port`.
- **SG egress:** `0.0.0.0/0` → **scoped** to the palace (spine-internal) + the EC2 Synapse's private IP over
  peering. No public egress (there is none in the no-NAT VPC).
- **AS registration `url`:** not the Cloud Map `nc-channels.<ns>` (unresolvable from the default VPC) →
  nc-channels' **peering-reachable private endpoint**.
- **`enable_comms_tier` coupling:** the held TF references `aws_security_group.synapse[0]`, which no longer
  exists (synapse.tf disarmed, #78). The re-target removes that reference entirely.

## Recommendation
**Option B (spine VPC + VPC peering to the EC2 box's private IP).** Rationale, in the session's discipline:
1. **Palace hop internal** — the memory path (Bar 2, the thing that's hard) is the easy hop, and the palace
   is now *proven* reachable+functional in-VPC.
2. **D2-compliant** — off both the runtime and the production Synapse box.
3. **Serves Bar 1 and Bar 2 identically** — no throwaway placement, no rework (the session's "build to the
   real target, not a smoke-only shortcut" ethos).
4. **No-NAT is respected** — peering-to-private-IP avoids needing a NAT gateway or public egress.

**If** you want a *fast Bar-1-only echo smoke* before committing the peering build, Option A (on-box, no
palace, no peering) gets first contact quickest — but flag it as **throwaway**, and don't let "it worked
on-box" become the accidental permanent placement. My lean is to do the peering once (Option B) and reach
Bar 1 on the footing Bar 2 also needs.

## Open sub-decisions for the box session (named, not improvised)
- Peering vs PrivateLink for default↔spine (peering is simpler for bidirectional TCP).
- The AS `url` = nc-channels' stable private endpoint (ENI static IP vs internal NLB — NLB if the ECS task IP
  churns).
- Whether to **split the orchestrator** into a spine-VPC HTTP service `nc-channels` calls (makes `nc-channels`
  a *thin* transport that could then live on-box without carrying the runtime) — a bigger change, deferable
  past Bar 1, but the clean long-term shape (the held TF's own comment flags it).
