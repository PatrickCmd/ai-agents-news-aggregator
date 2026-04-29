data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# OIDC provider created in infra/bootstrap/.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# Cross-module read: the remix state-machine ARN created by infra/scheduler/.
data "terraform_remote_state" "scheduler" {
  backend = "s3"
  config = {
    bucket  = "news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
    key     = "scheduler/terraform.tfstate"
    region  = "us-east-1"
    profile = "aiengineer"
  }
  workspace = terraform.workspace
}
