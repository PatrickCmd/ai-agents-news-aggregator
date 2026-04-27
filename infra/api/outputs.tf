output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "function_arn" {
  value = aws_lambda_function.api.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.api.name
}

output "api_endpoint" {
  description = "Base URL for the HTTP API ($default stage)."
  value       = aws_apigatewayv2_api.api.api_endpoint
}
