variable "aws_region" {
  description = "AWS region for state bucket + lock table"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "aiengineer"
}
