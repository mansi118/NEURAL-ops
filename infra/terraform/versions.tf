# NEOS production substrate — provider + version pins.
# Build-to-the-wall: this module is `terraform validate`-clean offline. `terraform apply` is the
# human gate (needs an AWS account + credentials); validate proves the HCL, not that the infra works.
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state is the operator's choice; left local here so `validate` needs no backend.
  # backend "s3" { ... }   # ← uncomment + configure at apply time (their gate).
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      Env       = var.environment
      ManagedBy = "terraform"
      Component = "neos-runtime"
    }
  }
}
