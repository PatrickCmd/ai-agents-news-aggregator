output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "ssm_param_name" {
  value = aws_ssm_parameter.alerts_topic_arn.name
}
