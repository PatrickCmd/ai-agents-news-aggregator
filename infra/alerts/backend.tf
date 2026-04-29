terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.42"
    }
  }
  backend "s3" {
    # Init: terraform init -backend-config="bucket=news-aggregator-tf-state-<acct>"
    #                      -backend-config="key=alerts/terraform.tfstate"
    #                      -backend-config="region=us-east-1"
    #                      -backend-config="profile=aiengineer"
    use_lockfile = true
  }
}

provider "aws" {
  region  = "us-east-1"
  profile = "aiengineer"
}
