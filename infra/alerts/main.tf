resource "aws_sns_topic" "alerts" {
  name = "news-alerts-${terraform.workspace}"

  tags = { Project = "news-aggregator", Module = "alerts" }
}

# Email subscription only in prod — dev/test alarms fire to a topic with no
# subscribers (visible in CloudWatch dashboard, no email noise).
resource "aws_sns_topic_subscription" "email_prod" {
  count     = terraform.workspace == "prod" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# SSM Parameter — every service module reads this to wire its alarm_actions.
# Plain String (not SecureString) — ARN isn't a secret.
resource "aws_ssm_parameter" "alerts_topic_arn" {
  name  = "/news-aggregator/${terraform.workspace}/sns-alerts-arn"
  type  = "String"
  value = aws_sns_topic.alerts.arn

  tags = { Project = "news-aggregator", Module = "alerts" }
}
