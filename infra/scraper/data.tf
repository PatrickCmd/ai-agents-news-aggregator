data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# OIDC provider created in infra/bootstrap/.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

data "aws_vpc" "target" {
  default = var.vpc_id == null
  id      = var.vpc_id
}

data "aws_subnets" "default_vpc" {
  count = var.subnet_ids == null ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.target.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

locals {
  resolved_subnet_ids = (
    var.subnet_ids != null
    ? var.subnet_ids
    : data.aws_subnets.default_vpc[0].ids
  )
}
