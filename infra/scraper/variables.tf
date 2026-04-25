variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile"
  type        = string
  default     = "aiengineer"
}

variable "cluster_name" {
  description = "ECS cluster name (shared across sub-projects)"
  type        = string
  default     = "news-aggregator"
}

variable "ecr_repo_name" {
  description = "ECR repository for the scraper image"
  type        = string
  default     = "news-scraper"
}

variable "image_tag" {
  description = "ECR image tag to deploy. Overridden by deploy.py with git SHA."
  type        = string
  default     = "latest"
}

variable "task_cpu" {
  description = "Fargate task vCPU units (256/512/1024/2048/4096)"
  type        = number
  default     = 2048
}

variable "task_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 4096
}

variable "min_capacity" {
  description = "Min number of ECS tasks"
  type        = number
  default     = 0
}

variable "max_capacity" {
  description = "Max number of ECS tasks"
  type        = number
  default     = 2
}

variable "scale_in_cooldown_seconds" {
  description = "Scale-in cooldown, protects long-running background tasks"
  type        = number
  default     = 1800
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention"
  type        = number
  default     = 14
}

variable "vpc_id" {
  description = "VPC ID for the service. Null = use default VPC."
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Subnet IDs for the service. Null = use default VPC subnets."
  type        = list(string)
  default     = null
}
