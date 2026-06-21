# Graphiti bridge (L2) + FalkorDB sidecar. The bridge is INTERNAL — called by Convex (in-VPC, per the
# self-host lean), reached via Cloud Map private DNS (bridge.<ns>), never the public ALB. FalkorDB runs
# as a sidecar in the same task (shared localhost; no service-to-service hop) and persists to EFS.

resource "aws_security_group" "bridge" {
  name        = "${local.name}-bridge-sg"
  description = "Bridge port from inside the VPC only (Convex → bridge); egress for Anthropic/Convex."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Bridge HTTP from in-VPC callers (Convex)"
    from_port   = var.bridge_container_port
    to_port     = var.bridge_container_port
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-bridge-sg" }
}

resource "aws_cloudwatch_log_group" "bridge" {
  name              = "/ecs/${local.name}-bridge"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

# Internal service discovery: bridge.<project>-<env>.local
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${local.name}.local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "bridge" {
  name = "bridge"

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

resource "aws_ecs_task_definition" "bridge" {
  family                   = "${local.name}-bridge"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.bridge_task_cpu
  memory                   = var.bridge_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "falkordb-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.falkordb.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.falkordb.id
        iam             = "DISABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "bridge"
      image     = var.bridge_image
      essential = true
      dependsOn = [{ containerName = "falkordb", condition = "START" }]

      portMappings = [{ containerPort = var.bridge_container_port, protocol = "tcp" }]

      environment = [
        { name = "BRIDGE_ENV", value = var.environment },
        { name = "FALKORDB_HOST", value = "127.0.0.1" },
        { name = "FALKORDB_PORT", value = "6379" },
        # L2 tenant-scope + the unified-audit emit are CONFIG toggles (default off; flipped at activation).
        { name = "BRIDGE_IDENTITY_ENABLED", value = tostring(var.enable_bridge_identity) },
        { name = "CONVEX_DENIAL_SINK_URL", value = var.convex_site_url },
      ]

      secrets = [
        { name = "PALACE_BRIDGE_API_KEY", valueFrom = aws_secretsmanager_secret.runtime["PALACE_BRIDGE_API_KEY"].arn },
        { name = "ANTHROPIC_API_KEY", valueFrom = aws_secretsmanager_secret.runtime["ANTHROPIC_API_KEY"].arn },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.bridge.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "bridge"
        }
      }
    },
    {
      name      = "falkordb"
      image     = var.falkordb_image
      essential = true

      # localhost only — never published to the ALB or the VPC; the bridge talks to it at 127.0.0.1:6379.
      mountPoints = [{ sourceVolume = "falkordb-data", containerPath = "/data", readOnly = false }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.bridge.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "falkordb"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "bridge" {
  name            = "${local.name}-bridge"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.bridge.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.bridge.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.bridge.arn
  }
}
