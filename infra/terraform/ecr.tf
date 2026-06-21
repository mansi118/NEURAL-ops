# Container registries — one per image (runtime + bridge). Immutable tags + scan-on-push so a
# deployed digest is pinned and CVE-scanned. The image-build CI pushes here (P1); apply creates them.

resource "aws_ecr_repository" "runtime" {
  name                 = "${local.name}-runtime"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

resource "aws_ecr_repository" "bridge" {
  name                 = "${local.name}-bridge"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

# Expire untagged images after 14 days to keep the registry bounded (same lifecycle on both).
locals {
  ecr_lifecycle = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "expire untagged after 14d"
      selection    = { tagStatus = "untagged", countType = "sinceImagePushed", countUnit = "days", countNumber = 14 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_ecr_lifecycle_policy" "runtime" {
  repository = aws_ecr_repository.runtime.name
  policy     = local.ecr_lifecycle
}

resource "aws_ecr_lifecycle_policy" "bridge" {
  repository = aws_ecr_repository.bridge.name
  policy     = local.ecr_lifecycle
}
