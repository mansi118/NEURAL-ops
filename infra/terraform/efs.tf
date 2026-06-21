# EFS — durable storage for FalkorDB (the advisory graph runs as a sidecar in the bridge task; its
# RDB/AOF persists here so a task restart doesn't lose the graph). KMS-encrypted, mount targets in each
# private subnet, reachable only from the bridge task SG over NFS (2049).

resource "aws_efs_file_system" "falkordb" {
  creation_token = "${local.name}-falkordb"
  encrypted      = true
  kms_key_id     = aws_kms_key.main.arn

  tags = { Name = "${local.name}-falkordb-efs" }
}

resource "aws_security_group" "efs" {
  name        = "${local.name}-efs-sg"
  description = "EFS NFS (2049) from the bridge task only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "NFS from bridge task"
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.bridge.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-efs-sg" }
}

resource "aws_efs_mount_target" "falkordb" {
  count           = var.az_count
  file_system_id  = aws_efs_file_system.falkordb.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# Access point — the FalkorDB container mounts this (uid/gid + root dir), so it never sees the FS root.
resource "aws_efs_access_point" "falkordb" {
  file_system_id = aws_efs_file_system.falkordb.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/falkordb"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "750"
    }
  }

  tags = { Name = "${local.name}-falkordb-ap" }
}
