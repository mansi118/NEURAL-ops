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
    "ANTHROPIC_API_KEY",
    "PALACE_BRIDGE_API_KEY",
    "CONVEX_SELF_HOSTED_ADMIN_KEY",
    "CONVEX_INSTANCE_SECRET",
  ]
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
variable "synapse_server_name" {
  description = "Matrix server_name (e.g. neuraledge.in)."
  type        = string
  default     = "neuraledge.local"
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
