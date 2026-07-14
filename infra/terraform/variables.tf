variable "project" {
  description = "Project tag / name prefix."
  type        = string
  default     = "neos"
}

variable "environment" {
  description = "Deployment environment (dogfood | staging | prod)."
  type        = string
  default     = "dogfood"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "ap-south-1"
}

variable "enable_nat_gateway" {
  description = <<-EOT
    Egress for the private subnets via a NAT gateway (needs 1 Elastic IP). Default true.
    Set false to use VPC endpoints (ECR/S3/Logs/Secrets Manager) instead — no EIP required
    (use when the account is at its EIP quota) and cheaper, but no public-internet egress
    in-private (fine for the spine: Convex image is mirrored to ECR; model/embedder deferred).
  EOT
  type        = bool
  default     = true
}

variable "enable_runtime_alb" {
  description = <<-EOT
    Register the runtime service behind the ALB target group (HTTP health-checked). Default true.
    The runtime is an idle worker until transport arrives (S0.3 nc-channels) — it serves no HTTP yet,
    so for the dogfood spine set false: the runtime runs as a worker (no health-check kill); the ALB
    stays provisioned for when transport lands.
  EOT
  type        = bool
  default     = true
}

variable "enable_comms_tier" {
  description = <<-EOT
    Provision the comms/audit/event tier (ElastiCache · NATS · ClickHouse · Synapse + RDS).
    Default true = the full substrate. Set false for the minimal dogfood SPINE (VPC + ALB +
    Convex + runtime + bridge only) — a reproducible scope flip, not a one-off `-target`.
  EOT
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = "CIDR for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of AZs to span (public+private subnet per AZ)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3 (ALB needs >=2 AZs)."
  }
}

variable "runtime_image" {
  description = "Container image for the NEOS runtime (ECR URI or registry ref). Built from the S0.1 Dockerfile."
  type        = string
  default     = "PLACEHOLDER.dkr.ecr.ap-south-1.amazonaws.com/neos-runtime:latest"
}

variable "container_port" {
  description = "Port the runtime container listens on (health + API)."
  type        = number
  default     = 8080
}

variable "desired_count" {
  description = "Number of Fargate tasks."
  type        = number
  default     = 1
}

variable "task_cpu" {
  description = "Fargate task CPU units (256|512|1024|2048|4096)."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Fargate task memory (MiB)."
  type        = number
  default     = 1024
}

variable "convex_site_url" {
  description = "Convex .convex.site URL the runtime broker targets (self-host proxy or cloud)."
  type        = string
  default     = ""
}

# The secret NAMES the runtime needs; VALUES are set out-of-band post-apply (never in TF state).
variable "managed_secret_keys" {
  description = "Secret keys provisioned in Secrets Manager (empty values; set after apply)."
  type        = list(string)
  # NOTE: the embedder credential is NOT here — embeddings compute server-side in Convex (D1), so the
  # key lives in the Convex deployment env (`convex env set GEMINI_API_KEY`), never injected into the
  # runtime container. (Removed vestigial EMBEDDER_API_KEY — T1.5; nothing in the runtime read it.)
  default = [
    "ANTHROPIC_API_KEY",  # kept as fallback (selfcheck fallback path); empty unless ML supplies one
    "OPENROUTER_API_KEY", # M2/D2: the live runtime LLM key (primary, CLASSIFIER_PROVIDER=openrouter)
    "PALACE_BRIDGE_API_KEY",
    "CONVEX_SELF_HOSTED_ADMIN_KEY",
    "CONVEX_INSTANCE_SECRET",
  ]
}

variable "llm_provider" {
  description = <<-EOT
    Runtime LLM provider (selfcheck CLASSIFIER_PROVIDER). M2/D2: "openrouter" is the forced V1 choice —
    no Anthropic key on hand + Bedrock blocked (see docs/decisions/ADR-llm.md). Set "anthropic" only if
    ML supplies a direct Anthropic key. The corresponding key must be a managed secret (above).
  EOT
  type        = string
  default     = "openrouter"
}

# ── Self-host Convex (the SoT) ──────────────────────────────────
variable "convex_image" {
  description = "Self-hosted Convex backend image (ECR or registry). The convex-local-backend."
  type        = string
  default     = "PLACEHOLDER.dkr.ecr.ap-south-1.amazonaws.com/neos-convex:latest"
}

variable "convex_instance_name" {
  description = "Convex self-hosted instance name."
  type        = string
  default     = "neos-self-hosted"
}

variable "convex_task_cpu" {
  description = "Fargate CPU for the Convex task."
  type        = number
  default     = 1024
}

variable "convex_task_memory" {
  description = "Fargate memory (MiB) for the Convex task."
  type        = number
  default     = 2048
}

variable "health_check_path" {
  description = "ALB target-group health check path."
  type        = string
  default     = "/health"
}

# ── Bridge (L2 Graphiti) + FalkorDB ─────────────────────────────
variable "bridge_image" {
  description = "Container image for the Graphiti bridge (ECR URI). Built from Mempalace services/Dockerfile."
  type        = string
  default     = "PLACEHOLDER.dkr.ecr.ap-south-1.amazonaws.com/neos-bridge:latest"
}

variable "falkordb_image" {
  description = "FalkorDB image (Redis-compatible graph; advisory layer, sidecar of the bridge task)."
  type        = string
  default     = "falkordb/falkordb:latest"
}

variable "bridge_container_port" {
  description = "Port the bridge listens on (matches services/Dockerfile: uvicorn --port 8100)."
  type        = number
  default     = 8100
}

variable "bridge_task_cpu" {
  description = "Fargate CPU for the bridge task (bridge + FalkorDB sidecar)."
  type        = number
  default     = 1024
}

variable "bridge_task_memory" {
  description = "Fargate memory (MiB) for the bridge task."
  type        = number
  default     = 2048
}

variable "enable_bridge_identity" {
  description = "L2 tenant-scope enforcement at the bridge (BRIDGE_IDENTITY_ENABLED). Default off — flipped at activation."
  type        = bool
  default     = false
}

variable "enable_bedrock" {
  description = "Grant the task role bedrock:InvokeModel (embeddings via Titan). Off if self-hosting the embedder."
  type        = bool
  default     = true
}

# ── TLS (gated: both must be set, else ALB stays HTTP-only) ──────
variable "domain_name" {
  description = "FQDN for the ALB (e.g. gateway.neuraledge.in). Blank ⇒ no TLS (HTTP-only, dev)."
  type        = string
  default     = ""
}

variable "route53_zone_id" {
  description = "Route53 hosted-zone id for DNS validation + the A-alias. Blank ⇒ no TLS."
  type        = string
  default     = ""
}

# ── Comms/audit/event tier ──────────────────────────────────────
variable "redis_node_type" {
  description = "ElastiCache Redis node type."
  type        = string
  default     = "cache.t4g.micro"
}

variable "nats_image" {
  description = "NATS server image (event bus)."
  type        = string
  default     = "nats:2-alpine"
}

variable "clickhouse_image" {
  description = "ClickHouse server image (audit-at-scale)."
  type        = string
  default     = "clickhouse/clickhouse-server:24-alpine"
}
variable "clickhouse_task_cpu" {
  description = "Fargate CPU for ClickHouse."
  type        = number
  default     = 1024
}
variable "clickhouse_task_memory" {
  description = "Fargate memory (MiB) for ClickHouse."
  type        = number
  default     = 4096
}
variable "synapse_image" {
  description = "Matrix Synapse image (nc-channels homeserver)."
  type        = string
  default     = "matrixdotorg/synapse:latest"
}

# ⛔ Structural disarm of the Fargate Synapse (ADR-matrix-homeserver, 2026-07-05). The canonical homeserver
# is the EXISTING EC2 Synapse at matrix.neuraledge.in, NOT synapse.tf. This var gates every synapse.tf
# resource (via local.synapse_enabled) and defaults false + is set by NO tfvars, so phase2 can never rebuild
# the redundant Synapse that was mistakenly applied + reverted on 2026-07-05. Do not set true without
# superseding the ADR.
variable "enable_fargate_synapse" {
  description = "RETIRED — do not enable. Gates the superseded Fargate synapse.tf. See ADR-matrix-homeserver."
  type        = bool
  default     = false
}
variable "synapse_server_name" {
  description = <<-EOT
    Matrix server_name — IMMUTABLE at Synapse first boot (baked into every mxid). Default is the safe
    non-resolvable placeholder; the comms-tier tfvars (phase2/phase3) override it to the real
    self-contained name "matrix.neuraledge.in" (G-A, element-first-contact-runbook). Set it correctly
    BEFORE the first comms-tier apply — it cannot be changed without destroying the homeserver.
  EOT
  type        = string
  default     = "neuraledge.local"
}

# ── nc-channels AS transport service (HELD — see nc-channels.tf) ──
variable "enable_nc_channels" {
  description = <<-EOT
    Bring up the nc-channels Matrix AS service. HELD at false: service.serve()/_cs_api_call() still raise
    NotImplementedError (transport-deploy-design D1 — proven at the box against live Synapse, never a mock),
    so flipping this true before that transport is hand-proven deploys a crash-looping task. Flip ONLY in
    the live window, AFTER _cs_api_call round-trips by hand. Requires enable_comms_tier=true (needs Synapse).
  EOT
  type        = bool
  default     = false
}
variable "nc_channels_image" {
  description = <<-EOT
    Container image for the nc-channels AS service. Likely the SAME app image as runtime_image (frontdoor +
    runtime are called in-process by orchestrator.handle → dispatch) with a `serve()` entrypoint — the exact
    entrypoint is a box-build detail of transport-deploy-design 3b, undetermined until serve() exists.
  EOT
  type        = string
  default     = "PLACEHOLDER.dkr.ecr.ap-south-1.amazonaws.com/neos-nc-channels:latest"
}
variable "nc_channels_port" {
  description = "Port nc-channels listens on for HS→AS transactions (PUT /_matrix/app/v1/transactions/{txnId})."
  type        = number
  default     = 8010
}

# ── Hermes seat wrapper (wrapper.tf) — the NEop-executing service in the spine VPC (Decision 2). ──────────
variable "enable_wrapper" {
  description = <<-EOT
    Bring up the Hermes seat wrapper (pi-neop-runtime, /seat/turn) in the spine VPC. HELD at false — same
    posture as enable_nc_channels: present on main, inert until a conscious flip. The seat refuses to start
    without FORWARD_TOKEN and refuses to wire live brokers without T9 ack, so deploying before those are
    provisioned + the inbound reach is decided (no matrix↔spine peering exists) is a refuse-then-restart task.
    Flip ONLY in the deploy window, with the bearer + FORWARD_TOKEN provisioned and wrapper_ingress_cidrs set.
    Requires the no-NAT endpoints (enable_nat_gateway=false → aws_security_group.vpce[0]).
  EOT
  type        = bool
  default     = false
}
variable "enable_recon_seat" {
  description = <<-EOT
    Add a SECOND wrapper seat for the `recon` NEop (agents/recon) alongside the primary seat. Additive: the
    per-seat resources are for_each'd over the seats map; the first (primary) seat keeps byte-identical names
    so it is never recreated. recon shares the FORWARD_TOKEN, model bearer, and jail SG; it gets its own
    task-def, service, and Cloud Map name (seat-wrapper-recon). Default false.
  EOT
  type        = bool
  default     = false
}
variable "wrapper_t9_ack" {
  description = <<-EOT
    Sets NEOP_T9_ACK=yes on the wrapper — i.e. CROSSES T9 (the first live NEop turn). HELD at false: default
    means the deployed wrapper boots and REFUSES to serve live, so the T9 gate holds even against an accidental
    deploy. Flipping true is the conscious first-live-turn crossing (plan-first, in the T9 window), distinct
    from merely deploying the service (enable_wrapper). STOP-AND-ASK before flipping.
  EOT
  type        = bool
  default     = false
}
variable "wrapper_image" {
  description = "The pi-neop-runtime GAP-2 jail image (ECR, pulled in-VPC via the ECR endpoint). Set at box-build."
  type        = string
  default     = "PLACEHOLDER.dkr.ecr.ap-south-1.amazonaws.com/pi-neop-runtime:latest"
}
variable "wrapper_port" {
  description = "Port the wrapper serves /seat/turn on (nrt serve-seat SEAT_PORT)."
  type        = number
  default     = 8090
}
variable "wrapper_provider" {
  description = <<-EOT
    Model provider for the wrapper: "amazon-bedrock" (DEFAULT — sealed spine, Nova via the in-VPC PrivateLink
    endpoint + bearer) or "openrouter" (a PUBLIC gateway — simplest provisioning, ONE api key, but ⚠️ UN-SEALS
    the wrapper's egress: it requires enable_nat_gateway=true and opens 443 to the internet, trading away the
    GAP-2 sealed-egress posture for speed. Fast-dogfood path, not the sealed one). Runtime supports both (#8).
  EOT
  type        = string
  default     = "amazon-bedrock"
  validation {
    condition     = contains(["amazon-bedrock", "openrouter"], var.wrapper_provider)
    error_message = "wrapper_provider must be amazon-bedrock or openrouter."
  }
}
variable "wrapper_model_id" {
  description = "Bedrock model id for the wrapper (parameterized — Claude-on-Bedrock becomes a config change if un-gated)."
  type        = string
  default     = "apac.amazon.nova-lite-v1:0" # APAC inference profile; bare amazon.nova-* rejects on-demand
}
variable "wrapper_openrouter_model" {
  description = "OpenRouter model id (used when wrapper_provider=openrouter). Provider-prefixed, e.g. anthropic/claude-3.5-haiku."
  type        = string
  default     = "anthropic/claude-3.5-haiku"
}

# ── Two-model NEop loop (SEAT_MODEL_FAST / SEAT_MODEL_QUALITY) ────────────────────────────────────────────
# The seat reply path runs a defined Haiku(fast)+Sonnet(quality) loop (pi-neop-runtime seat/loop.ts): Haiku
# grounds memory + guards the draft, Sonnet writes the answer. These pin the two model ids per provider. They
# override only the REPLY loop; the task path still rides NRT_MODEL (wrapper_model_id). On amazon-bedrock these
# are the regional/global inference-profile ids the on-demand Converse invoke needs (bare ids reject).
variable "wrapper_model_fast" {
  description = "Bedrock inference-profile id for the FAST tier (Haiku) — memory grounding + draft guard in the seat reply loop."
  type        = string
  default     = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}
variable "wrapper_model_quality" {
  description = "Bedrock inference-profile id for the QUALITY tier (Sonnet) — the user-facing answer in the seat reply loop."
  type        = string
  default     = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
}
variable "wrapper_openrouter_model_fast" {
  description = "OpenRouter FAST-tier id (Haiku) when wrapper_provider=openrouter. Box-verify it's a live pi-ai openrouter id."
  type        = string
  default     = "anthropic/claude-3.5-haiku"
}
variable "wrapper_openrouter_model_quality" {
  description = "OpenRouter QUALITY-tier id (Sonnet) when wrapper_provider=openrouter. Box-verify it's a live pi-ai openrouter id."
  type        = string
  default     = "anthropic/claude-3.5-sonnet"
}
variable "wrapper_palace_mcp_url" {
  description = "The palace /mcp endpoint the wrapper calls — the IN-VPC Cloud Map Convex (e.g. http://convex.<ns>.local:3211/mcp), NOT the external .convex.site (no NAT to reach it)."
  type        = string
  default     = ""
}
variable "wrapper_palace_id" {
  description = "Wrapper scope: palaceId (tenant). Baked from env, never from the request payload."
  type        = string
  default     = ""
}
variable "wrapper_neop_id" {
  description = "Wrapper scope: neopId (the seat). Baked from env, never from payload. Must NOT be a reserved identity (_admin/_system)."
  type        = string
  default     = ""
}
variable "wrapper_neop_path" {
  description = "The seat's NEop folder (e.g. agents/recon)."
  type        = string
  default     = "agents/recon"
}
variable "wrapper_memory_min_score" {
  description = "Relevance gate for retrieved memory (SEAT_MEMORY_MIN_SCORE, reply.ts). 0 = off (server floor only). Measured live: on-topic ~1.07-1.14, off-topic ~0.19; 1.0 keeps real hits."
  type        = number
  default     = 0
}
variable "wrapper_ingress_cidrs" {
  description = <<-EOT
    Source CIDR(s) permitted to POST /seat/turn (the bridge, FORWARD_TOKEN-authenticated). DEFAULT [] ⇒ the
    wrapper is UNREACHABLE (fail-closed). §INBOUND is resolved toward PEERING (peering.tf): set this to the
    matrix/bridge source CIDR when peering is up, so the SG admits the bridge over the peered path. Deliberately
    NOT defaulted to a public/wide source; the peering gives the route, this gives the scoped SG allowance.
  EOT
  type        = list(string)
  default     = []
}

# ── matrix↔spine VPC peering (peering.tf) — the wrapper's INBOUND path, §INBOUND resolved toward peering. ──
variable "enable_matrix_peering" {
  description = <<-EOT
    Bring up the matrix-box(default VPC)↔spine VPC peering + routes (peering.tf + the inline spine route in
    network.tf). HELD at false. The sealed-spine inbound: the bridge reaches the wrapper over the peered
    INTERNAL path — no public surface. Flip in the deploy window; requires matrix_vpc_id/_cidr/_route_table_id
    set together (the matrix VPC is a separate EC2 box, not managed here). Same account + region assumed.
  EOT
  type        = bool
  default     = false
}
variable "matrix_vpc_id" {
  description = "The matrix-server box's default VPC id (peering accepter). Required when enable_matrix_peering=true."
  type        = string
  default     = ""
}
variable "matrix_vpc_cidr" {
  description = "The matrix VPC's CIDR — the spine's return route destination + the bridge's source for wrapper_ingress_cidrs."
  type        = string
  default     = ""
}
variable "matrix_route_table_id" {
  description = "The matrix VPC's route table id, for the matrix→spine return route. Required when enable_matrix_peering=true."
  type        = string
  default     = ""
}
variable "synapse_task_cpu" {
  description = "Fargate CPU for Synapse."
  type        = number
  default     = 512
}
variable "synapse_task_memory" {
  description = "Fargate memory (MiB) for Synapse."
  type        = number
  default     = 1024
}
variable "synapse_db_instance_class" {
  description = "RDS instance class for the Synapse Postgres backend."
  type        = string
  default     = "db.t4g.micro"
}

# ── Fidelity scheduler (Track 3 — the nightly curator fold; see fidelity.tf) ──────────────────────────
variable "enable_fidelity_scheduler" {
  description = "Deploy the EventBridge-scheduled fidelity-fold Fargate task (held false; merging is inert)."
  type        = bool
  default     = false
}
variable "fidelity_schedule" {
  description = "EventBridge Scheduler cron for the curator fold. Default: nightly 03:00 UTC."
  type        = string
  default     = "cron(0 3 * * ? *)"
}
variable "fidelity_seats" {
  description = "Comma-separated seat neopIds to fold each run (e.g. 'aria,recon')."
  type        = string
  default     = "aria,recon"
}
variable "fidelity_palace_id" {
  description = "The tenant/palaceId whose seats the fold runs for (the dogfood palace)."
  type        = string
  default     = ""
}
variable "fidelity_convex_url" {
  description = "CONVEX_DEPLOYMENT_URL for the runner's palace reach (in-VPC Convex base, memory.py appends /mcp). Blank ⇒ falls back to convex_site_url."
  type        = string
  default     = ""
}
variable "fidelity_judge_model" {
  description = "Bedrock inference-profile id for the LLM-as-judge (Claude Haiku). Empty ⇒ runtime.bedrock default."
  type        = string
  default     = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}

# ── Vault scheduler (Track 3 — the nightly promotion cadence; see vault-scheduler.tf) ─────────────────
variable "enable_vault_scheduler" {
  description = "Deploy the EventBridge-scheduled vault-promote Fargate task (held false; merging is inert)."
  type        = bool
  default     = false
}
variable "vault_schedule" {
  description = "EventBridge Scheduler cron for the vault promotion pass. Default: nightly 04:00 UTC."
  type        = string
  default     = "cron(0 4 * * ? *)"
}
variable "vault_seats" {
  description = "Comma-separated seat neopIds to run the vault promotion for (e.g. 'aria,recon')."
  type        = string
  default     = "aria,recon"
}
