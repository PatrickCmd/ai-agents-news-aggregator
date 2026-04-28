# Read the per-env SNS topic ARN exported by infra/alerts/.
data "aws_ssm_parameter" "alerts_arn" {
  name = "/news-aggregator/${terraform.workspace}/sns-alerts-arn"
}

resource "aws_cloudwatch_metric_alarm" "email_errors" {
  alarm_name          = "news-email-${terraform.workspace}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Lambda news-email-${terraform.workspace} returned ≥1 unhandled error in 5min."
  alarm_actions       = [data.aws_ssm_parameter.alerts_arn.value]

  dimensions = {
    FunctionName = aws_lambda_function.this.function_name
  }
}

resource "aws_cloudwatch_metric_alarm" "email_throttles" {
  alarm_name          = "news-email-${terraform.workspace}-throttles"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  alarm_description   = "Lambda news-email-${terraform.workspace} hit concurrency throttle ≥1× in 5min."
  alarm_actions       = [data.aws_ssm_parameter.alerts_arn.value]

  dimensions = {
    FunctionName = aws_lambda_function.this.function_name
  }
}
