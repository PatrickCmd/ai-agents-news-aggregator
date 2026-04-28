data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Existing wildcard ACM cert (in us-east-1 — required for CloudFront).
data "aws_acm_certificate" "wildcard" {
  domain      = "*.patrickcmd.dev"
  statuses    = ["ISSUED"]
  most_recent = true
}

# Existing Route 53 hosted zone for the parent domain.
data "aws_route53_zone" "parent" {
  name = "patrickcmd.dev."
}

# OIDC provider created in infra/bootstrap/.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}
