# fidelity scheduler — the nightly CURATOR FOLD (Track 3). An EventBridge Scheduler fires a Fargate
# RunTask that runs the Python `runtime/fidelity_runner.py` CLI: read each seat's run_events (shadow
# predictions + human verdicts) + twin off the palace, fold via the Curator, write the twin back. The
# runner is otherwise a CLI nobody calls; THIS is the cadence that advances agreement_rate_30d.
#
# AUTHORED-BUT-HELD on var.enable_fidelity_scheduler (default false) — same posture as wrapper.tf /
# nc-channels.tf: present on main, inert until a conscious flip. A plan against main shows ZERO fidelity
# resources, so merging changes nothing live.
#
# SCOPE/REACH: runs in the spine private subnets on the SAME runtime image + task/execution roles +
# managed secrets as aws_ecs_task_definition.runtime, so it inherits the palace reach (CONVEX_* → the
# in-VPC Convex /mcp, via runtime/memory.py) and, IF AWS_BEARER_TOKEN_BEDROCK is a managed secret, the
# Claude-Haiku judge (runtime/bedrock.py). No bearer ⇒ the runner simply leaves the ambiguous middle
# UNSCORED (never fabricated) — the human-verdict signal still folds. No inbound; egress = palace only.

locals {
  fidelity_enabled = var.enable_fidelity_scheduler ? 1 : 0
}

resource "aws_cloudwatch_log_group" "fidelity" {
  count             = local.fidelity_enabled
  name              = "/ecs/${local.name}-fidelity"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "fidelity" {
  count                    = local.fidelity_enabled
  family                   = "${local.name}-fidelity"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "fidelity"
      image     = var.runtime_image # same NEURAL-ops Python image; different COMMAND (the runner CLI)
      essential = true
      # One pass over the tenant's seats, then EXIT (a scheduled batch, not a service) — the runner's
      # __main__ reads PALACE_ID + FIDELITY_SEATS from env and writes the twin back per should_persist.
      command = ["python3", "runtime/fidelity_runner.py"]

      environment = [
        { name = "NEOS_ENV", value = var.environment },
        # Palace reach for the Python runtime (memory.py posts CONVEX_DEPLOYMENT_URL|CONVEX_SITE_URL + /mcp).
        { name = "CONVEX_DEPLOYMENT_URL", value = var.fidelity_convex_url },
        { name = "CONVEX_SITE_URL", value = var.convex_site_url },
        { name = "PALACE_ID", value = var.fidelity_palace_id },  # the tenant whose seats we fold
        { name = "FIDELITY_SEATS", value = var.fidelity_seats }, # comma-separated neopIds (e.g. aria,recon)
        { name = "FIDELITY_JUDGE_MODEL", value = var.fidelity_judge_model },
        { name = "AWS_REGION", value = var.region },
      ]

      # Same managed secrets as the runtime — if AWS_BEARER_TOKEN_BEDROCK is among them, the judge is live.
      secrets = [
        for k in var.managed_secret_keys : {
          name      = k
          valueFrom = aws_secretsmanager_secret.runtime[k].arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.fidelity[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "fidelity"
        }
      }
    },
  ])
}

# ── EventBridge Scheduler → ECS RunTask (the cadence) ─────────────────────────────────────────────────
# The scheduler needs a role that can RunTask the fidelity task-def and PassRole its exec+task roles.
data "aws_iam_policy_document" "fidelity_scheduler_assume" {
  count = local.fidelity_enabled
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fidelity_scheduler" {
  count              = local.fidelity_enabled
  name               = "${local.name}-fidelity-scheduler"
  assume_role_policy = data.aws_iam_policy_document.fidelity_scheduler_assume[0].json
}

data "aws_iam_policy_document" "fidelity_scheduler" {
  count = local.fidelity_enabled
  statement {
    sid       = "RunFidelityTask"
    actions   = ["ecs:RunTask"]
    resources = ["${aws_ecs_task_definition.fidelity[0].arn_without_revision}:*"]
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

resource "aws_iam_role_policy" "fidelity_scheduler" {
  count  = local.fidelity_enabled
  name   = "${local.name}-fidelity-scheduler"
  role   = aws_iam_role.fidelity_scheduler[0].id
  policy = data.aws_iam_policy_document.fidelity_scheduler[0].json
}

resource "aws_scheduler_schedule" "fidelity_fold" {
  count = local.fidelity_enabled
  name  = "${local.name}-fidelity-fold"

  flexible_time_window {
    mode = "OFF"
  }
  schedule_expression          = var.fidelity_schedule # default: nightly (curator fold cadence)
  schedule_expression_timezone = "Etc/UTC"

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.fidelity_scheduler[0].arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.fidelity[0].arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = aws_subnet.private[*].id
        security_groups  = [aws_security_group.service.id]
        assign_public_ip = false
      }
    }

    # Batch never runs twice on a hiccup: no retries here — the next nightly fold subsumes a missed one.
    retry_policy {
      maximum_retry_attempts = 0
    }
  }
}
