# ElastiCache (Redis) — managed cache/queue for the nc-* services (sessions, rate-limit, ephemeral
# queues). Private subnets, reachable in-VPC only; KMS-encrypted at rest. Single node for dogfood
# (automatic_failover off); add a replica + failover for prod HA.

resource "aws_elasticache_subnet_group" "main" {
  count      = var.enable_comms_tier ? 1 : 0
  name       = "${local.name}-redis"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "redis" {
  count       = var.enable_comms_tier ? 1 : 0
  name        = "${local.name}-redis-sg"
  description = "Redis 6379 from in-VPC callers only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Redis from in-VPC"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-redis-sg" }
}

resource "aws_elasticache_replication_group" "main" {
  count                = var.enable_comms_tier ? 1 : 0
  replication_group_id = "${local.name}-redis"
  description          = "NEOS Redis (nc-* sessions / queues / cache)"
  engine               = "redis"
  node_type            = var.redis_node_type
  num_cache_clusters   = 1
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main[0].name
  security_group_ids   = [aws_security_group.redis[0].id]

  at_rest_encryption_enabled = true
  kms_key_id                 = aws_kms_key.main.arn
  transit_encryption_enabled = false # in-VPC + SG-locked; enable (with an auth token) for prod hardening

  automatic_failover_enabled = false # single node (dogfood); add a replica + failover for HA
}

output "redis_endpoint" {
  description = "Redis primary endpoint (in-VPC); null when the comms tier is disabled."
  value       = var.enable_comms_tier ? aws_elasticache_replication_group.main[0].primary_endpoint_address : null
}
