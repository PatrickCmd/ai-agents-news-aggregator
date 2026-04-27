# IAM role for EventBridge to start cron-pipeline executions.
resource "aws_iam_role" "cron_trigger" {
  name = "news-cron-trigger-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "cron_trigger" {
  role = aws_iam_role.cron_trigger.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.cron.arn
    }]
  })
}

# Daily cron at 21:00 UTC = 00:00 EAT.
resource "aws_cloudwatch_event_rule" "cron" {
  name                = "news-cron-pipeline-${terraform.workspace}"
  description         = "Daily news pipeline trigger (00:00 EAT = 21:00 UTC)"
  schedule_expression = "cron(0 21 * * ? *)"
  state               = "ENABLED"
  tags                = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_cloudwatch_event_target" "cron" {
  rule     = aws_cloudwatch_event_rule.cron.name
  arn      = aws_sfn_state_machine.cron.arn
  role_arn = aws_iam_role.cron_trigger.arn
}

# CloudWatch alarms — fail + stale.
resource "aws_cloudwatch_metric_alarm" "cron_failed" {
  alarm_name          = "news-cron-pipeline-failed-${terraform.workspace}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "news-cron-pipeline state machine status FAILED/TIMED_OUT"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.cron.arn
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_cloudwatch_metric_alarm" "cron_stale" {
  alarm_name          = "news-cron-pipeline-stale-${terraform.workspace}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsSucceeded"
  namespace           = "AWS/States"
  period              = 129600
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "news-cron-pipeline has not had a successful run in 36h"
  treat_missing_data  = "breaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.cron.arn
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}
