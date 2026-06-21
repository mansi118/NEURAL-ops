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

  load_balancer {
    target_group_arn = aws_lb_target_group.runtime.arn
    container_name   = "runtime"
    container_port   = var.container_port
  }

  depends_on = [aws_lb_listener.http]
}
