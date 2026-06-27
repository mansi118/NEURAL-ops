# VPC endpoints — used when enable_nat_gateway=false (no public egress in-private). They give the
# private-subnet tasks a path to the AWS services the spine needs WITHOUT a NAT/EIP:
#   S3 (gateway, free)        — ECR image layers live in S3
#   ECR api + dkr (interface) — pull images from ECR
#   CloudWatch Logs (iface)   — task logging
#   Secrets Manager (iface)   — runtime/convex secrets injection
# Convex's image is mirrored ghcr.io -> ECR (build.sh mirror-convex) so no public pull is needed.
# Model/embedder egress is deferred, so the spine needs no other internet.

locals {
  use_endpoints = var.enable_nat_gateway ? 0 : 1
  iface_services = var.enable_nat_gateway ? [] : [
    "ecr.api",
    "ecr.dkr",
    "logs",
    "secretsmanager",
  ]
}

resource "aws_security_group" "vpce" {
  count       = local.use_endpoints
  name        = "${local.name}-vpce-sg"
  description = "HTTPS (443) from in-VPC to the interface VPC endpoints."
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS from in-VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name}-vpce-sg" }
}

# S3 gateway endpoint — attached to the private route table (free; required for ECR layer pulls).
resource "aws_vpc_endpoint" "s3" {
  count             = local.use_endpoints
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${local.name}-s3-vpce" }
}

# Interface endpoints (one per service) — private DNS so the standard SDK endpoints resolve in-VPC.
resource "aws_vpc_endpoint" "iface" {
  for_each            = toset(local.iface_services)
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpce[0].id]
  private_dns_enabled = true
  tags                = { Name = "${local.name}-${each.value}-vpce" }
}
