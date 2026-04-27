# Connection used by the cron pipeline's HTTP tasks for the scraper.
# AWS requires Authorization headers — we pass a dummy API_KEY since the scraper
# endpoint is internal-public. If a real auth header is needed later, swap in.
resource "aws_cloudwatch_event_connection" "scraper" {
  name               = "news-scraper-${terraform.workspace}"
  authorization_type = "API_KEY"
  auth_parameters {
    api_key {
      key   = "X-Internal-Token"
      value = "unused"
    }
  }
}

# IAM role for the cron-pipeline state machine.
resource "aws_iam_role" "cron_sm" {
  name = "news-cron-pipeline-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "cron_sm_invoke" {
  role = aws_iam_role.cron_sm.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-digest-${terraform.workspace}",
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}",
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}",
          aws_lambda_function.this.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = "states:InvokeHTTPEndpoint"
        Resource = "arn:aws:states:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:stateMachine:news-cron-pipeline-${terraform.workspace}"
        Condition = {
          StringEquals = {
            "states:HTTPMethod" = ["GET", "POST"]
          }
          StringLike = {
            "states:HTTPEndpoint" = [
              "${var.scraper_base_url}/ingest",
              "${var.scraper_base_url}/runs/*",
            ]
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "events:RetrieveConnectionCredentials"
        Resource = aws_cloudwatch_event_connection.scraper.arn
      },
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = aws_cloudwatch_event_connection.scraper.secret_arn
      },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "cron_sm" {
  name              = "/aws/states/news-cron-pipeline-${terraform.workspace}"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "cron" {
  name     = "news-cron-pipeline-${terraform.workspace}"
  role_arn = aws_iam_role.cron_sm.arn
  type     = "STANDARD"
  definition = templatefile("${path.module}/templates/cron_pipeline.asl.json", {
    scraper_base_url            = var.scraper_base_url
    scraper_connection_arn      = aws_cloudwatch_event_connection.scraper.arn
    scheduler_lambda_arn        = aws_lambda_function.this.arn
    news_digest_arn             = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-digest-${terraform.workspace}"
    news_editor_arn             = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}"
    news_email_arn              = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}"
    digest_max_concurrency      = var.digest_max_concurrency
    editor_max_concurrency      = var.editor_max_concurrency
    email_max_concurrency       = var.email_max_concurrency
    scraper_poll_max_iterations = var.scraper_poll_max_iterations
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.cron_sm.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}

# IAM role for the remix-user state machine — narrower scope.
resource "aws_iam_role" "remix_sm" {
  name = "news-remix-user-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "remix_sm_invoke" {
  role = aws_iam_role.remix_sm.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}",
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "remix_sm" {
  name              = "/aws/states/news-remix-user-${terraform.workspace}"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "remix" {
  name     = "news-remix-user-${terraform.workspace}"
  role_arn = aws_iam_role.remix_sm.arn
  type     = "STANDARD"
  definition = templatefile("${path.module}/templates/remix_user.asl.json", {
    news_editor_arn = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}"
    news_email_arn  = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}"
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.remix_sm.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}
