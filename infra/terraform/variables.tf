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
  default = [
    "ANTHROPIC_API_KEY",
    "EMBEDDER_API_KEY",
    "PALACE_BRIDGE_API_KEY",
    "CONVEX_SELF_HOSTED_ADMIN_KEY",
  ]
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
  description = "Port the bridge listens on."
  type        = number
  default     = 8000
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
