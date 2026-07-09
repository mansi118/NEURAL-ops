# Two roles, least-privilege:
#  - execution role: ECS agent pulls the image + writes logs + READS the secrets at task start.
#  - task role: the app's own AWS identity at runtime (empty policy here; attach per-integration).

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Scope secret reads to exactly the runtime secrets (not account-wide) + decrypt them with the CMK.
data "aws_iam_policy_document" "secrets_read" {
  statement {
    sid       = "ReadRuntimeSecrets"
    actions   = ["secretsmanager:GetSecretValue"]
    # runtime secrets + the wrapper secrets (empty set unless enable_wrapper, so backward-compatible).
    # The wrapper's ECS task pulls WRAPPER_FORWARD_TOKEN + the model bearer at launch via THIS exec role;
    # omitting them is a ResourceInitializationError (AccessDenied) that crash-loops the wrapper.
    resources = concat(
      [for s in aws_secretsmanager_secret.runtime : s.arn],
      [for s in aws_secretsmanager_secret.wrapper : s.arn],
    )
  }
  statement {
    sid       = "DecryptSecretsCMK"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.main.arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "${local.name}-secrets-read"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.secrets_read.json
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Embeddings via Bedrock Titan (gated — off if self-hosting the embedder). Scoped to InvokeModel.
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid       = "BedrockInvokeEmbeddings"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/amazon.titan-embed-text-v2:0"]
  }
}

resource "aws_iam_role_policy" "task_bedrock" {
  count  = var.enable_bedrock ? 1 : 0
  name   = "${local.name}-bedrock-invoke"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}
