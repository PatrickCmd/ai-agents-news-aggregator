data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# OIDC provider created in infra/bootstrap/.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}
