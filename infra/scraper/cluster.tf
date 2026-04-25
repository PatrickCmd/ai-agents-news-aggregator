resource "aws_ecs_cluster" "main" {
  name = var.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Project = "news-aggregator"
  }
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/ecs/${var.ecr_repo_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}
