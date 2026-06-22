# NATS — the event bus for nc-* services (publish/subscribe, request/reply). INTERNAL (Cloud Map
# nats.<ns>:4222). Ephemeral for dogfood (no JetStream persistence); add an EFS volume + `-js -sd /data`
# when durable streams are needed (named follow-up). Lightweight; one task.

resource "aws_security_group" "nats" {
  name        = "${local.name}-nats-sg"
  description = "NATS 4222 (client) from in-VPC callers only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "NATS clients from in-VPC"
    from_port   = 4222
    to_port     = 4222
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-nats-sg" }
}

resource "aws_cloudwatch_log_group" "nats" {
  name              = "/ecs/${local.name}-nats"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_service_discovery_service" "nats" {
  name = "nats"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_ecs_task_definition" "nats" {
  family                   = "${local.name}-nats"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name         = "nats"
      image        = var.nats_image
      essential    = true
      portMappings = [{ containerPort = 4222, protocol = "tcp" }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.nats.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "nats"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "nats" {
  name            = "${local.name}-nats"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.nats.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.nats.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.nats.arn
  }
}
