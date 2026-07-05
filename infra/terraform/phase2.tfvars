# M3·T3.2 — Phase 2: SUBSTRATE. Foundation + the comms/audit tier + the live embedder.
#   adds ElastiCache · NATS · ClickHouse · Synapse + RDS, and turns the embedder on.
# Still NO L2 identity enforcement (governance flip is Phase 3) — this is the full data substrate
# running, before enforcement is hardened. Supersets phase1: apply over a phase1 stack to scope up.
#
# Apply (⛔ human gate — adds ~30 billing resources):
#   terraform plan  -var-file=phase2.tfvars -out tf.plan   # expect ~90 resources (comms tier present)
#   terraform apply tf.plan

environment = "dogfood"
region      = "ap-south-1"

# ── Scope toggles: substrate = data/comms tier up, enforcement still off ──
enable_nat_gateway     = false # still VPC-endpoints; embedder reaches Bedrock via PrivateLink (no NAT/EIP)
enable_comms_tier      = true  # ElastiCache/NATS/ClickHouse/Synapse/RDS — the full audit/event/channel substrate
enable_runtime_alb     = false # runtime worker until transport lands; flip with S0.3 nc-channels
enable_bedrock         = true  # embedder LIVE — Titan via the bedrock-runtime VPC endpoint (PrivateLink)
enable_bridge_identity = false # governance enforcement still deferred to Phase 3

convex_image = "ghcr.io/get-convex/convex-backend:latest"

# runtime_image = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-runtime@sha256:..."
# bridge_image  = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-bridge@sha256:..."

# ── G-A (element-first-contact-runbook) — Matrix server_name, set BEFORE the first comms-tier apply ──
# Synapse bakes server_name into every mxid (@seat:<server_name>) permanently at first boot; it CANNOT
# change afterward without destroying the homeserver — so it must be correct before THIS apply, not fixed
# during activation. Overrides the safe `.local` default (variables.tf:250).
# CHOICE: the SELF-CONTAINED name (server_name == the homeserver's own address), NOT the `neuraledge.in`
# delegation form. The homeserver is then authoritative for its own name, so clients + federation need NO
# `.well-known/matrix/*` file on any apex domain — one fewer permanent dependency, and the smallest live
# window (nothing to discover at first contact). G-B becomes plain public ingress at
# https://matrix.neuraledge.in (this same name), no delegation. Tradeoff accepted: mxids read
# @seat:matrix.neuraledge.in, and immutability means no later switch to a bare-apex mxid — fine for alpha.
synapse_server_name = "matrix.neuraledge.in"

# domain_name     = ""
# route53_zone_id = ""
