locals {
  sensitive_env = [
    "supabase_db_url",
    "supabase_pooler_url",
    "openai_api_key",
    "langfuse_public_key",
    "langfuse_secret_key",
    "youtube_proxy_username",
    "youtube_proxy_password",
    "resend_api_key",
  ]
}

resource "aws_ssm_parameter" "sensitive" {
  for_each = toset(local.sensitive_env)

  name        = "/news-aggregator/${terraform.workspace}/${each.value}"
  description = "Sensitive env for the scraper service (${terraform.workspace})"
  type        = "SecureString"
  value       = "placeholder-set-via-sync-secrets" # pragma: allowlist secret

  lifecycle {
    # Real values are pushed by infra/scraper/sync_secrets.py — never Terraform-managed.
    ignore_changes = [value]
  }

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}
