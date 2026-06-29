resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/ecs/${local.name}-runtime"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_cluster" "main" {
  name = "${local.name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "runtime" {
  family                   = "${local.name}-runtime"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.task_cpu
  memory                   = var.task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "runtime"
      image     = var.runtime_image
      essential = true

      portMappings = [
        { containerPort = var.container_port, protocol = "tcp" },
      ]

      # Non-secret config inline; secret VALUES injected from Secrets Manager at task start.
      environment = [
        { name = "NEOS_ENV", value = var.environment },
        { name = "CONVEX_SITE_URL", value = var.convex_site_url },
        # M2/D2: runtime LLM provider = OpenRouter (forced — no Anthropic key + Bedrock blocked; ADR-llm).
        # selfcheck reads CLASSIFIER_PROVIDER → requires OPENROUTER_API_KEY (a managed secret).
        { name = "CLASSIFIER_PROVIDER", value = var.llm_provider },
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
          "awslogs-group"         = aws_cloudwatch_log_group.runtime.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "runtime"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "runtime" {
  name            = "${local.name}-runtime"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.runtime.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  # The runtime serves no HTTP until transport (S0.3); gate the ALB registration so an idle worker
  # isn't killed by health checks. enable_runtime_alb=false ⇒ runs as a worker; ALB stays for later.
  dynamic "load_balancer" {
    for_each = var.enable_runtime_alb ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.runtime.arn
      container_name   = "runtime"
      container_port   = var.container_port
    }
  }

  depends_on = [aws_lb_listener.http]
}
