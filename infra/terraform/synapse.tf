# Matrix Synapse (nc-channels homeserver) + its RDS Postgres backend. Built INTERNAL (Cloud Map
# synapse.<ns>:8008 client API); RDS Postgres is the durable store (manage_master_user_password ⇒ the
# password lives in an RDS-managed Secrets Manager secret, never in TF). Synapse signing keys + media
# persist on EFS.
#
# NAMED ACTIVATION STEP: the client API (8008) must become PUBLIC for seats' Matrix clients to connect —
# an ALB host rule (matrix.<domain>) + TLS + federation (8448) if used. That ingress is wired at activation
# (P3), not here; this builds the substrate (Synapse + RDS + EFS) internal-first, validate-clean.

resource "aws_db_subnet_group" "synapse" {
  count      = var.enable_comms_tier ? 1 : 0
  name       = "${local.name}-synapse-db"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "synapse_db" {
  count       = var.enable_comms_tier ? 1 : 0
  name        = "${local.name}-synapse-db-sg"
  description = "Postgres 5432 from the Synapse task only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from Synapse"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.synapse[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-synapse-db-sg" }
}

resource "aws_db_instance" "synapse" {
  count                       = var.enable_comms_tier ? 1 : 0
  identifier                  = "${local.name}-synapse"
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = var.synapse_db_instance_class
  allocated_storage           = 20
  db_name                     = "synapse"
  username                    = "synapse"
  manage_master_user_password = true # password → RDS-managed Secrets Manager secret, never in TF
  db_subnet_group_name        = aws_db_subnet_group.synapse[0].name
  vpc_security_group_ids      = [aws_security_group.synapse_db[0].id]
  storage_encrypted           = true
  kms_key_id                  = aws_kms_key.main.arn
  multi_az                    = false # dogfood; multi_az + a read replica for prod HA
  backup_retention_period     = 7
  skip_final_snapshot         = true # dogfood; set false + final_snapshot_identifier for prod
}

# EFS — Synapse signing keys + media (must persist across task restarts).
resource "aws_efs_file_system" "synapse" {
  count          = var.enable_comms_tier ? 1 : 0
  creation_token = "${local.name}-synapse"
  encrypted      = true
  kms_key_id     = aws_kms_key.main.arn
  tags           = { Name = "${local.name}-synapse-efs" }
}

resource "aws_security_group" "synapse" {
  count       = var.enable_comms_tier ? 1 : 0
  name        = "${local.name}-synapse-sg"
  description = "Synapse client API (8008) from in-VPC (the gateway/nc-channels); egress to RDS/EFS."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Synapse client API from in-VPC"
    from_port   = 8008
    to_port     = 8008
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-synapse-sg" }
}

resource "aws_security_group" "synapse_efs" {
  count       = var.enable_comms_tier ? 1 : 0
  name        = "${local.name}-synapse-efs-sg"
  description = "EFS NFS (2049) from the Synapse task only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from Synapse task"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.synapse[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-synapse-efs-sg" }
}

resource "aws_efs_mount_target" "synapse" {
  count           = var.enable_comms_tier ? var.az_count : 0
  file_system_id  = aws_efs_file_system.synapse[0].id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.synapse_efs[0].id]
}

resource "aws_efs_access_point" "synapse" {
  count          = var.enable_comms_tier ? 1 : 0
  file_system_id = aws_efs_file_system.synapse[0].id

  posix_user {
    uid = 991
    gid = 991
  }

  root_directory {
    path = "/synapse"
    creation_info {
      owner_uid   = 991
      owner_gid   = 991
      permissions = "750"
    }
  }

  tags = { Name = "${local.name}-synapse-ap" }
}

resource "aws_service_discovery_service" "synapse" {
  count = var.enable_comms_tier ? 1 : 0
  name  = "synapse"

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

resource "aws_cloudwatch_log_group" "synapse" {
  count             = var.enable_comms_tier ? 1 : 0
  name              = "/ecs/${local.name}-synapse"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "synapse" {
  count                    = var.enable_comms_tier ? 1 : 0
  family                   = "${local.name}-synapse"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.synapse_task_cpu
  memory                   = var.synapse_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "synapse-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.synapse[0].id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.synapse[0].id
        iam             = "DISABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name         = "synapse"
      image        = var.synapse_image
      essential    = true
      portMappings = [{ containerPort = 8008, protocol = "tcp" }]

      environment = [
        { name = "SYNAPSE_SERVER_NAME", value = var.synapse_server_name },
        { name = "SYNAPSE_REPORT_STATS", value = "no" },
        { name = "POSTGRES_HOST", value = aws_db_instance.synapse[0].address },
        { name = "POSTGRES_DB", value = "synapse" },
        { name = "POSTGRES_USER", value = "synapse" },
      ]

      # Postgres password from the RDS-managed secret (JSON → the `password` field only).
      secrets = [
        { name = "POSTGRES_PASSWORD", valueFrom = "${aws_db_instance.synapse[0].master_user_secret[0].secret_arn}:password::" },
      ]

      mountPoints = [{ sourceVolume = "synapse-data", containerPath = "/data", readOnly = false }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.synapse[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "synapse"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "synapse" {
  count           = var.enable_comms_tier ? 1 : 0
  name            = "${local.name}-synapse"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.synapse[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.synapse[0].id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.synapse[0].arn
  }
}
