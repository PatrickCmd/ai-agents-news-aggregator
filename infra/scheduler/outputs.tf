output "function_name" { value = aws_lambda_function.this.function_name }
output "function_arn" { value = aws_lambda_function.this.arn }
output "log_group_name" { value = aws_cloudwatch_log_group.lambda.name }
output "scraper_base_url" { value = var.scraper_base_url }

output "cron_state_machine_arn" {
  description = "ARN of the cron-pipeline state machine (consumed by Make targets)"
  value       = aws_sfn_state_machine.cron.arn
}

output "remix_state_machine_arn" {
  description = "ARN of the remix-user state machine (REQUIRED by #4 — its API Lambda will StartExecution on this)"
  value       = aws_sfn_state_machine.remix.arn
}

output "scheduler_lambda_arn" {
  description = "Alias for function_arn — name #4's API Lambda will read via remote state"
  value       = aws_lambda_function.this.arn
}
