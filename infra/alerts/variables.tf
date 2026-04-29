variable "alert_email" {
  type        = string
  description = "Email subscribed to the prod SNS topic. Unused for dev/test workspaces."
  default     = ""

  validation {
    # Allow empty for dev/test (no subscription), require non-empty in prod.
    # Terraform 1.6 doesn't support workspace-aware validation, so this is
    # a soft check; the prod apply will fail if the email is empty because
    # `aws_sns_topic_subscription` rejects an empty endpoint.
    condition     = length(var.alert_email) == 0 || can(regex("^[^@]+@[^@]+\\.[^@]+$", var.alert_email))
    error_message = "alert_email must be a valid email address or empty."
  }
}
