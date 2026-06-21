# Customer-managed KMS key — encrypts Secrets Manager, ECR images, EFS, and CloudWatch logs. One CMK
# for the deployment (per-tenant CMKs are a multi-tenant hardening step). Rotation on; the default key
# policy (account root + the granted service principals via grants) governs use.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_kms_key" "main" {
  description             = "${local.name} CMK — secrets · ECR · EFS · logs"
  enable_key_rotation     = true
  deletion_window_in_days = 14

  # Allow the account root (IAM-delegated) + CloudWatch Logs in this region to use the key.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountRoot"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${data.aws_region.current.name}.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
        Resource  = "*"
      },
    ]
  })
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.main.key_id
}
