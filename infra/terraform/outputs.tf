output "alb_dns_name" {
  description = "Public DNS of the ALB (point your domain's CNAME here)."
  value       = aws_lb.main.dns_name
}

output "cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.main.name
}

output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.runtime.name
}

output "vpc_id" {
  description = "VPC id."
  value       = aws_vpc.main.id
}

output "secret_arns" {
  description = "Map of secret key -> ARN. Set each value post-apply with `aws secretsmanager put-secret-value`."
  value       = { for k, s in aws_secretsmanager_secret.runtime : k => s.arn }
}

output "log_group" {
  description = "CloudWatch log group for the runtime."
  value       = aws_cloudwatch_log_group.runtime.name
}
