output "state_bucket_name" {
  description = "Name of the S3 bucket holding Terraform state for all modules"
  value       = aws_s3_bucket.tf_state.bucket
}

output "lock_table_name" {
  description = "Name of the DynamoDB table used for state locking"
  value       = aws_dynamodb_table.tf_lock.name
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "lambda_artifacts_bucket" {
  description = "S3 bucket holding per-agent Lambda zip artifacts"
  value       = aws_s3_bucket.lambda_artifacts.bucket
}
