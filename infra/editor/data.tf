data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "terraform_remote_state" "bootstrap" {
  backend = "s3"
  config = {
    bucket  = "news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
    key     = "bootstrap/terraform.tfstate"
    region  = "us-east-1"
    profile = var.aws_profile
  }
}
