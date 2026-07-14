# vault scheduler — the nightly VAULT-PROMOTER cadence (Track 3, sibling of the fidelity fold in
# fidelity.tf). An EventBridge Scheduler fires a Fargate RunTask that runs `runtime/vault_runner.py`:
# read each seat's candidate writes (run_events kind=memory_candidate) + Decision-Queue approvals
# (human_verdict) + the vault_promoted markers (#32), run the five gates, land promoted records durably
# (palace_remember). Same held-behind-a-flag posture as fidelity.tf — a plan against main shows ZERO
# vault resources, so merging is inert. Reuses the runtime image + task/exec roles + managed secrets.

locals {
  vault_enabled = var.enable_vault_scheduler ? 1 : 0
}

resource "aws_cloudwatch_log_group" "vault" {
  count             = local.vault_enabled
  name              = "/ecs/${local.name}-vault"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "vault" {
  count                    = local.vault_enabled
  family                   = "${local.name}-vault"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "vault"
      image     = var.runtime_image # same NEURAL-ops Python image; command = the vault runner CLI
      essential = true
      command   = ["python3", "runtime/vault_runner.py"]

      environment = [
        { name = "NEOS_ENV", value = var.environment },
        { name = "CONVEX_DEPLOYMENT_URL", value = var.fidelity_convex_url }, # palace reach (memory.py + /mcp)
        { name = "CONVEX_SITE_URL", value = var.convex_site_url },
        { name = "PALACE_ID", value = var.fidelity_palace_id }, # same dogfood palace as the fidelity fold
        { name = "VAULT_SEATS", value = var.vault_seats },      # comma-separated neopIds
        { name = "AWS_REGION", value = var.region },
      ]

      secrets = [
        for k in var.managed_secret_keys : {
          name      = k
          valueFrom = aws_secretsmanager_secret.runtime[k].arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.vault[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "vault"
        }
      }
    },
  ])
}

# ── EventBridge Scheduler → ECS RunTask ────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "vault_scheduler_assume" {
  count = local.vault_enabled
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "vault_scheduler" {
  count              = local.vault_enabled
  name               = "${local.name}-vault-scheduler"
  assume_role_policy = data.aws_iam_policy_document.vault_scheduler_assume[0].json
}

data "aws_iam_policy_document" "vault_scheduler" {
  count = local.vault_enabled
  statement {
    sid       = "RunVaultTask"
    actions   = ["ecs:RunTask"]
    resources = ["${aws_ecs_task_definition.vault[0].arn_without_revision}:*"]
    condition {
      test     = "ArnLike"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.main.arn]
    }
  }
  statement {
    sid       = "PassTaskRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
  }
}

resource "aws_iam_role_policy" "vault_scheduler" {
  count  = local.vault_enabled
  name   = "${local.name}-vault-scheduler"
  role   = aws_iam_role.vault_scheduler[0].id
  policy = data.aws_iam_policy_document.vault_scheduler[0].json
}

resource "aws_scheduler_schedule" "vault_promote" {
  count = local.vault_enabled
  name  = "${local.name}-vault-promote"

  flexible_time_window {
    mode = "OFF"
  }
  schedule_expression          = var.vault_schedule
  schedule_expression_timezone = "Etc/UTC"

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.vault_scheduler[0].arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.vault[0].arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = aws_subnet.private[*].id
        security_groups  = [aws_security_group.service.id]
        assign_public_ip = false
      }
    }

    retry_policy {
      maximum_retry_attempts = 0 # the next nightly pass subsumes a miss
    }
  }
}
