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
