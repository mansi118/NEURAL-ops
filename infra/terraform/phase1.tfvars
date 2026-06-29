# M3·T3.2 — Phase 1: FOUNDATION (all tiers false). The cheapest scope that stands the substrate up.
#   = VPC (+ VPC endpoints, no NAT/EIP) + Convex SoT (self-host) + runtime worker + bridge (+FalkorDB).
# No comms/audit tier, no embedder, no ALB registration, no L2 identity enforcement. Everything that
# bills incrementally is deferred to phase2/phase3. Proves: the spine stands and the memory/ACL/audit
# smoke (tools/deployed_stack_smoke.py) is GREEN from in-VPC.
#
# Apply (⛔ G-c, human gate — real billing starts):
#   terraform plan  -var-file=phase1.tfvars -out tf.plan   # expect ~60 resources, comms tier absent
#   terraform apply tf.plan
# Fill runtime_image / bridge_image with the ECR digests the M3·T3.1 pipeline (build-push-ecr.yml) pushes.

environment = "dogfood"
region      = "ap-south-1"

# ── Scope toggles: foundation = everything off ──────────────────
enable_nat_gateway     = false # VPC endpoints only (ECR/S3/Logs/Secrets) — no EIP, cheaper; spine needs no public egress
enable_comms_tier      = false # drops ElastiCache/NATS/ClickHouse/Synapse/RDS (29 resources)
enable_runtime_alb     = false # runtime is an idle worker until transport (S0.3) — no health-check kill; ALB stays provisioned
enable_bedrock         = false # embedder deferred (no in-private Bedrock PrivateLink yet)
enable_bridge_identity = false # L2 tenant-scope enforcement flipped at activation (the governance gate)

# Convex SoT — public self-hosted backend image (matches the INSTANCE_NAME/INSTANCE_SECRET contract in convex.tf).
convex_image = "ghcr.io/get-convex/convex-backend:latest"

# Custom images — pin to the ECR digests pushed by build-push-ecr.yml (repo is IMMUTABLE; use @sha256, not :latest).
# runtime_image = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-runtime@sha256:..."
# bridge_image  = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-bridge@sha256:..."

# TLS deferred (HTTP-only dogfood). Set both to enable ACM/443/redirect.
# domain_name     = ""
# route53_zone_id = ""
