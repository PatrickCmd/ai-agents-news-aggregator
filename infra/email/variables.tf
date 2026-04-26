variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "aiengineer"
}

variable "zip_s3_key" {
  description = "S3 key inside the artifact bucket (e.g. email/<sha>.zip). Set by deploy.py."
  type        = string
}

variable "zip_sha256" {
  description = "Base64-encoded SHA256 of the zip — Lambda's source_code_hash."
  type        = string
}

variable "memory_size" {
  type    = number
  default = 1024
}

variable "timeout" {
  type    = number
  default = 120
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "openai_model" {
  type    = string
  default = "gpt-5.4-mini"
}

variable "mail_from" {
  description = "Resend-verified From: address"
  type        = string
}

variable "sender_name" {
  type    = string
  default = "AI News Digest"
}

variable "mail_to_default" {
  description = "Override To: for testing (empty in prod)"
  type        = string
  default     = ""
}
