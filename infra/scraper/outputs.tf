output "scraper_endpoint" {
  description = "Auto-provisioned HTTPS endpoint of the ECS Express service"
  value = try(
    aws_ecs_express_gateway_service.scraper.ingress_paths[0].endpoint,
    null,
  )
}

output "scraper_ingress_paths" {
  description = "All ingress paths (access_type + endpoint) for the Express service"
  value       = aws_ecs_express_gateway_service.scraper.ingress_paths
}

output "ecr_repo_url" {
  description = "ECR repository URL for pushing images"
  value       = aws_ecr_repository.scraper.repository_url
}

output "log_group_name" {
  description = "CloudWatch log group for scraper tasks"
  value       = aws_cloudwatch_log_group.scraper.name
}

output "environment" {
  description = "Terraform workspace (env) this deploy targets"
  value       = terraform.workspace
}
