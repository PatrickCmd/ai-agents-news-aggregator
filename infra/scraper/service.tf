resource "aws_ecs_express_gateway_service" "scraper" {
  service_name            = "scraper"
  cluster                 = aws_ecs_cluster.main.name
  execution_role_arn      = aws_iam_role.task_execution.arn
  infrastructure_role_arn = aws_iam_role.infrastructure.arn
  task_role_arn           = aws_iam_role.task.arn
  cpu                     = tostring(var.task_cpu)
  memory                  = tostring(var.task_memory)
  health_check_path       = "/healthz"
  wait_for_steady_state   = true

  network_configuration = [{
    subnets         = local.resolved_subnet_ids
    security_groups = []
  }]

  scaling_target = [{
    auto_scaling_metric       = "ECSServiceAverageCPUUtilization"
    auto_scaling_target_value = 70
    min_task_count            = var.min_capacity
    max_task_count            = var.max_capacity
  }]

  primary_container {
    image          = "${aws_ecr_repository.scraper.repository_url}:${var.image_tag}"
    container_port = 8000

    aws_logs_configuration {
      log_group = aws_cloudwatch_log_group.scraper.name
    }

    # Non-sensitive config
    environment {
      name  = "ENV"
      value = terraform.workspace
    }
    environment {
      name  = "LOG_LEVEL"
      value = "INFO"
    }
    environment {
      name  = "LOG_JSON"
      value = "true"
    }
    environment {
      name  = "OPENAI_MODEL"
      value = "gpt-5.4-mini"
    }
    environment {
      name  = "RSS_MCP_PATH"
      value = "/app/rss-mcp/dist/index.js"
    }
    environment {
      name  = "WEB_SEARCH_MAX_TURNS"
      value = "15"
    }
    environment {
      name  = "WEB_SEARCH_SITE_TIMEOUT"
      value = "120"
    }
    environment {
      name  = "YOUTUBE_TRANSCRIPT_CONCURRENCY"
      value = "3"
    }
    environment {
      name  = "RSS_FEED_CONCURRENCY"
      value = "5"
    }
    environment {
      name  = "WEB_SEARCH_SITE_CONCURRENCY"
      value = "2"
    }
    environment {
      name  = "YOUTUBE_PROXY_ENABLED"
      value = "true"
    }
    environment {
      name  = "LANGFUSE_HOST"
      value = "https://cloud.langfuse.com"
    }

    # Sensitive config via SSM SecureString
    secret {
      name       = "SUPABASE_DB_URL"
      value_from = aws_ssm_parameter.sensitive["supabase_db_url"].arn
    }
    secret {
      name       = "SUPABASE_POOLER_URL"
      value_from = aws_ssm_parameter.sensitive["supabase_pooler_url"].arn
    }
    secret {
      name       = "OPENAI_API_KEY"
      value_from = aws_ssm_parameter.sensitive["openai_api_key"].arn
    }
    secret {
      name       = "LANGFUSE_PUBLIC_KEY"
      value_from = aws_ssm_parameter.sensitive["langfuse_public_key"].arn
    }
    secret {
      name       = "LANGFUSE_SECRET_KEY"
      value_from = aws_ssm_parameter.sensitive["langfuse_secret_key"].arn
    }
    secret {
      name       = "YOUTUBE_PROXY_USERNAME"
      value_from = aws_ssm_parameter.sensitive["youtube_proxy_username"].arn
    }
    secret {
      name       = "YOUTUBE_PROXY_PASSWORD"
      value_from = aws_ssm_parameter.sensitive["youtube_proxy_password"].arn
    }
    secret {
      name       = "RESEND_API_KEY"
      value_from = aws_ssm_parameter.sensitive["resend_api_key"].arn
    }
  }

  depends_on = [aws_ssm_parameter.sensitive]

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}
