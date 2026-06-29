# M3·T3.2 — Phase 3: ENFORCEMENT. Substrate + L2 tenant-scope enforcement on (the governance flip).
#   = Phase 2 + enable_bridge_identity=true (BRIDGE_IDENTITY_ENABLED). The full, enforced scope.
# Supersets phase2. The flip is gated on docs/decisions/approval-policy-v1.md being set (see the
# deferred "governance flip" gate in the spine runbook) — do NOT apply this before that decision lands.
#
# Apply (⛔ human gate — governance flip; turns the enforcement boundary HARD):
#   terraform plan  -var-file=phase3.tfvars -out tf.plan
#   terraform apply tf.plan
#
# NOTE: signed identity (Gate D / S0.3 X-NEop-Identity) + pen-test remain separate activation gates
# above the Terraform layer — this flip enforces L2 tenant scope at the bridge, not the /mcp signature.

environment = "dogfood"
region      = "ap-south-1"

# ── Scope toggles: enforcement = everything on ──────────────────
enable_nat_gateway     = false # keep no-NAT unless a public-egress need is proven (NAT decision is separate)
enable_comms_tier      = true
enable_runtime_alb     = false # still worker-mode until transport; not coupled to the governance flip
enable_bedrock         = true
enable_bridge_identity = true # L2 tenant-scope enforcement ON — the governance flip

convex_image = "ghcr.io/get-convex/convex-backend:latest"

# runtime_image = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-runtime@sha256:..."
# bridge_image  = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-bridge@sha256:..."

# TLS — enable for any non-throwaway enforcement deploy.
# domain_name     = "gateway.neuraledge.in"
# route53_zone_id = "Z..."
