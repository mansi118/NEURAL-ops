# M3·T3.1 — GitHub Actions → OIDC → ECR. No long-lived AWS keys: GHA exchanges its OIDC token for a
# short-lived role session scoped to THIS repo. The role can ONLY push to the project's ECR repos.
#
# Apply is small + cheap (IAM only, no ongoing cost). `gha_repos` are the GitHub "owner/name" slugs.

variable "gha_repos" {
  description = <<-EOT
    GitHub repos allowed to assume the ECR-push role (owner/name). Both image builds need it:
    NEURAL-ops (runtime image) and Mempalace_NEOS (bridge image). The role's ECR-push permission is
    scoped to neos-dogfood-* regardless, so both repos push only to the project's repos.
  EOT
  type        = list(string)
  default     = ["mansi118/NEURAL-ops", "mansi118/Mempalace_NEOS"]
}

data "aws_caller_identity" "gha" {}

# GitHub's OIDC identity provider (one per account). AWS validates the cert chain itself now, but the
# resource still requires a thumbprint — both well-known GitHub values are listed for resilience.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
  tags = { Name = "github-actions-oidc" }
}

data "aws_iam_policy_document" "gha_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Only workflows in THESE repos (any branch/tag) may assume the role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [for r in var.gha_repos : "repo:${r}:*"]
    }
  }
}

data "aws_iam_policy_document" "gha_ecr_push" {
  statement {
    sid       = "EcrAuth"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # GetAuthorizationToken is account-scoped only
  }
  statement {
    sid    = "EcrPush"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:DescribeImages",
    ]
    # Scoped to the project's repos only — never the whole registry.
    resources = ["arn:aws:ecr:${var.region}:${data.aws_caller_identity.gha.account_id}:repository/${local.name}-*"]
  }
}

resource "aws_iam_role" "gha_ecr_push" {
  name               = "gha-ecr-push"
  assume_role_policy = data.aws_iam_policy_document.gha_trust.json
  tags               = { Name = "gha-ecr-push" }
}

resource "aws_iam_role_policy" "gha_ecr_push" {
  name   = "ecr-push"
  role   = aws_iam_role.gha_ecr_push.id
  policy = data.aws_iam_policy_document.gha_ecr_push.json
}

output "gha_ecr_push_role_arn" {
  description = "Role ARN the GHA workflow assumes (matches .github/workflows/build-push-ecr.yml)."
  value       = aws_iam_role.gha_ecr_push.arn
}
