terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.42.0"
    }
  }
  # No backend block -> local state. This is intentional (chicken-and-egg).
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

data "aws_caller_identity" "current" {}

locals {
  state_bucket_name = "news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
  lock_table_name   = "news-aggregator-tf-locks"
}

resource "aws_s3_bucket" "tf_state" {
  bucket = local.state_bucket_name

  tags = {
    Project = "news-aggregator"
    Purpose = "terraform-state"
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = local.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Project = "news-aggregator"
    Purpose = "terraform-lock"
  }
}
