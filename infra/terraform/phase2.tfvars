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

# domain_name     = ""
# route53_zone_id = ""
