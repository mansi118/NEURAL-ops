# ClickHouse — the audit-at-scale store (the Day-90 measurement substrate: denial/event analytics over
# the unified audit). INTERNAL (Cloud Map clickhouse.<ns>: 8123 HTTP / 9000 native), reachable in-VPC by
# the audit writers/readers. EFS-persisted; single node for dogfood (add a shard/replica for scale).

resource "aws_efs_file_system" "clickhouse" {
  count          = var.enable_comms_tier ? 1 : 0
  creation_token = "${local.name}-clickhouse"
  encrypted      = true
  kms_key_id     = aws_kms_key.main.arn
  tags           = { Name = "${local.name}-clickhouse-efs" }
}

resource "aws_security_group" "clickhouse" {
  count       = var.enable_comms_tier ? 1 : 0
  name        = "${local.name}-clickhouse-sg"
  description = "ClickHouse 8123 (HTTP) + 9000 (native) from in-VPC callers only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "ClickHouse HTTP from in-VPC"
    from_port   = 8123
    to_port     = 8123
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "ClickHouse native from in-VPC"
    from_port   = 9000
    to_port     = 9000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-clickhouse-sg" }
}

resource "aws_security_group" "clickhouse_efs" {
  count       = var.enable_comms_tier ? 1 : 0
  name        = "${local.name}-clickhouse-efs-sg"
  description = "EFS NFS (2049) from the ClickHouse task only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from ClickHouse task"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.clickhouse[0].id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-clickhouse-efs-sg" }
}

resource "aws_efs_mount_target" "clickhouse" {
  count           = var.enable_comms_tier ? var.az_count : 0
  file_system_id  = aws_efs_file_system.clickhouse[0].id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.clickhouse_efs[0].id]
}

resource "aws_efs_access_point" "clickhouse" {
  count          = var.enable_comms_tier ? 1 : 0
  file_system_id = aws_efs_file_system.clickhouse[0].id

  posix_user {
    uid = 101
    gid = 101
  }

  root_directory {
    path = "/clickhouse"
    creation_info {
      owner_uid   = 101
      owner_gid   = 101
      permissions = "750"
    }
  }

  tags = { Name = "${local.name}-clickhouse-ap" }
}

resource "aws_service_discovery_service" "clickhouse" {
  count = var.enable_comms_tier ? 1 : 0
  name  = "clickhouse"

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

resource "aws_cloudwatch_log_group" "clickhouse" {
  count             = var.enable_comms_tier ? 1 : 0
  name              = "/ecs/${local.name}-clickhouse"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_ecs_task_definition" "clickhouse" {
  count                    = var.enable_comms_tier ? 1 : 0
  family                   = "${local.name}-clickhouse"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.clickhouse_task_cpu
  memory                   = var.clickhouse_task_memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "clickhouse-data"
    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.clickhouse[0].id
      transit_encryption = "ENABLED"
      authorization_config {
        access_point_id = aws_efs_access_point.clickhouse[0].id
        iam             = "DISABLED"
      }
    }
  }

  container_definitions = jsonencode([
    {
      name      = "clickhouse"
      image     = var.clickhouse_image
      essential = true

      portMappings = [
        { containerPort = 8123, protocol = "tcp" },
        { containerPort = 9000, protocol = "tcp" },
      ]

      ulimits = [{ name = "nofile", softLimit = 262144, hardLimit = 262144 }]

      mountPoints = [{ sourceVolume = "clickhouse-data", containerPath = "/var/lib/clickhouse", readOnly = false }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.clickhouse[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "clickhouse"
        }
      }
    },
  ])
}

resource "aws_ecs_service" "clickhouse" {
  count           = var.enable_comms_tier ? 1 : 0
  name            = "${local.name}-clickhouse"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.clickhouse[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.clickhouse[0].id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.clickhouse[0].arn
  }
}
