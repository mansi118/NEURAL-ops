# bar2-live.tfvars — the EXACT vars the live Bar-2 wrapper+peering deploy was applied with
# (2026-07-09). Committing these so a future `terraform apply` reproduces the RUNNING state
# instead of reverting it. Secrets are NOT here (they live in Secrets Manager, set post-apply:
# WRAPPER_FORWARD_TOKEN, WRAPPER_AWS_BEARER_TOKEN_BEDROCK).
#
# Apply with: terraform apply -var-file=bar2-live.tfvars
# NOTE: wrapper_t9_ack=true here means an apply CROSSES/HOLDS T9 (the wrapper serves live). That is
# the conscious state as of the 2026-07-09 Bar-2 crossing; keep it deliberate.

enable_wrapper           = true
wrapper_image            = "071126865245.dkr.ecr.ap-south-1.amazonaws.com/neos-dogfood-wrapper:latest"
wrapper_provider         = "amazon-bedrock"
wrapper_palace_mcp_url   = "http://convex.neos-dogfood.local:3211/mcp"
wrapper_palace_id        = "k17f0b36y2f7h4sbr3pqp5wxg189cvg1"
wrapper_neop_id          = "aria"
wrapper_neop_path        = "agents/outreach"
wrapper_t9_ack           = true
wrapper_memory_min_score = 1.0  # relevance gate (live-measured: on-topic ~1.07-1.14, off-topic ~0.19)
enable_recon_seat        = true # SECOND seat: recon (agents/recon) — additive, aria untouched

enable_matrix_peering = true
matrix_vpc_id         = "vpc-03e47f7a8946ba248"
matrix_route_table_id = "rtb-00ab29fcf7ec99c4d"
matrix_vpc_cidr       = "172.31.0.0/16"
wrapper_ingress_cidrs = ["172.31.0.0/16"]

# ── Track 3 intelligence-loop schedulers (applied + verified live 2026-07-14) ──
# EventBridge → Fargate RunTask of the fidelity fold (nightly 03:00 UTC) + vault promote (04:00 UTC).
# fidelity_convex_url MUST be the :3211 SITE endpoint (the /mcp HTTP-actions port) — NOT the :3210 backend
# API port (that 404s). runtime_image for these task-defs is pinned in terraform.tfvars (gitignored);
# it MUST be an image built AFTER the runners existed (>= commit 8e88717 / sha256:c5e1f5df) or the task
# 'can't open runtime/fidelity_runner.py'. Both runners smoke-tested exit 0 against the live palace.
enable_fidelity_scheduler = true
enable_vault_scheduler    = true
fidelity_palace_id        = "k17f0b36y2f7h4sbr3pqp5wxg189cvg1"
fidelity_convex_url       = "http://convex.neos-dogfood.local:3211" # :3211 = /mcp site endpoint (NOT :3210)
convex_site_url           = "http://convex.neos-dogfood.local:3211"
vault_seats               = "aria,recon"
