# TLS — ACM cert (DNS-validated) + a 443 listener + an A-alias to the ALB. Variable-gated on a domain +
# a Route53 zone: when either is blank, TLS resources are skipped and the ALB stays HTTP-only (the dev
# default). When both are set, apply provisions the cert, validates it via DNS, terminates TLS at 443,
# and the HTTP listener (alb.tf) redirects 80→443.

locals {
  tls_enabled = var.domain_name != "" && var.route53_zone_id != ""
}

resource "aws_acm_certificate" "main" {
  count             = local.tls_enabled ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# DNS validation records in the hosted zone.
resource "aws_route53_record" "cert_validation" {
  for_each = local.tls_enabled ? {
    for dvo in aws_acm_certificate.main[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  } : {}

  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
}

resource "aws_acm_certificate_validation" "main" {
  count                   = local.tls_enabled ? 1 : 0
  certificate_arn         = aws_acm_certificate.main[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

resource "aws_lb_listener" "https" {
  count             = local.tls_enabled ? 1 : 0
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.runtime.arn
  }
}

# Point the domain at the ALB.
resource "aws_route53_record" "alb" {
  count   = local.tls_enabled ? 1 : 0
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}
