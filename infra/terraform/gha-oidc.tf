# M3·T3.1 — GitHub Actions → OIDC → ECR. No long-lived AWS keys: GHA exchanges its OIDC token for a
# short-lived role session scoped to THIS repo. The role can ONLY push to the project's ECR repos.
#
# Apply is small + cheap (IAM only, no ongoing cost). `gha_repo` is the GitHub "owner/name".

variable "gha_repo" {
  description = "GitHub repo allowed to assume the ECR-push role (owner/name)."
  type        = string
  default     = "mansi118/NEURAL-ops"
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
    # Only workflows in THIS repo (any branch/tag) may assume the role.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.gha_repo}:*"]
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
