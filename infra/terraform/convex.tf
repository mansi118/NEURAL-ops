# Self-host Convex (the SoT) on Fargate — what's proven on the self-host backend, now on AWS infra, for
# DPDP data sovereignty. INTERNAL only (Cloud Map private DNS, not the public ALB): the runtime + bridge
# reach it in-VPC at convex.<ns>:3211 (the .convex.site HTTP-actions port) and :3210 (the API). Persists
# to EFS (the sqlite DB + storage dir); desired_count = 1 (single writer — sqlite-on-EFS is fine for one
# task; move to a Postgres backend for multi-instance prod, see README).

resource "aws_efs_file_system" "convex" {
  creation_token = "${local.name}-convex"
  encrypted      = true
  kms_key_id     = aws_kms_key.main.arn
  tags           = { Name = "${local.name}-convex-efs" }
}

resource "aws_security_group" "convex" {
  name        = "${local.name}-convex-sg"
  description = "Convex API (3210) + site-proxy (3211) from in-VPC callers (runtime, bridge) only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Convex API + site-proxy from in-VPC"
    from_port   = 3210
    to_port     = 3211
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-convex-sg" }
}

resource "aws_security_group" "convex_efs" {
  name        = "${local.name}-convex-efs-sg"
  description = "EFS NFS (2049) from the Convex task only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from Convex task"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.convex.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-convex-efs-sg" }
}

resource "aws_efs_mount_target" "convex" {
  count           = var.az_count
  file_system_id  = aws_efs_file_system.convex.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.convex_efs.id]
}

resource "aws_efs_access_point" "convex" {
  file_system_id = aws_efs_file_system.convex.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/convex"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "750"
    }
  }

  tags = { Name = "${local.name}-convex-ap" }
}

# Internal DNS: convex.<project>-<env>.local (same namespace as the bridge).
resource "aws_service_discovery_service" "convex" {
  name = "convex"

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

resource "aws_cloudwatch_log_group" "convex" {
  name              = "/ecs/${local.name}-convex"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "convex" {
  family                   = "${local.name}-convex"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.convex_task_cpu
  memory                   = var.convex_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "convex-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.convex.id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.convex.id
        iam             = "DISABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name             = "convex"
      image            = var.convex_image
      essential        = true
      workingDirectory = "/convex"

      portMappings = [
        { containerPort = 3210, protocol = "tcp" }, # API
        { containerPort = 3211, protocol = "tcp" }, # site-proxy (.convex.site HTTP actions)
      ]

      environment = [
        { name = "INSTANCE_NAME", value = var.convex_instance_name },
        # The backend's externally-reachable origins (in-VPC Cloud Map) — used in storage URLs +
        # action callbacks. Plain HTTP in-VPC ⇒ DO_NOT_REQUIRE_SSL; no NAT ⇒ DISABLE_BEACON.
        { name = "CONVEX_CLOUD_ORIGIN", value = "http://convex.${aws_service_discovery_private_dns_namespace.main.name}:3210" },
        { name = "CONVEX_SITE_ORIGIN", value = "http://convex.${aws_service_discovery_private_dns_namespace.main.name}:3211" },
        { name = "DO_NOT_REQUIRE_SSL", value = "true" },
        { name = "DISABLE_BEACON", value = "true" },
      ]

      secrets = [
        { name = "INSTANCE_SECRET", valueFrom = aws_secretsmanager_secret.runtime["CONVEX_INSTANCE_SECRET"].arn },
      ]

      # Mount EFS at the DATA dir (/convex/data, per run_backend.sh), NOT /convex — mounting over
      # /convex would shadow the image's scripts (run_backend.sh / generate_admin_key.sh).
      mountPoints = [{ sourceVolume = "convex-data", containerPath = "/convex/data", readOnly = false }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.convex.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "convex"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "convex" {
  name            = "${local.name}-convex"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.convex.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.convex.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.convex.arn
  }
}

# The in-VPC site URL the runtime/bridge target. Wire into the runtime/bridge env via this output (or set
# convex_site_url = this value at apply time) so the broker keys on the self-hosted Convex.
output "convex_site_url" {
  description = "Internal Convex .convex.site URL (site-proxy) for the runtime/bridge."
  value       = "http://convex.${aws_service_discovery_private_dns_namespace.main.name}:3211"
}
