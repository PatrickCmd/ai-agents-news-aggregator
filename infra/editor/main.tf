locals {
  function_name = "news-editor-${terraform.workspace}"
  ssm_prefix    = "/news-aggregator/${terraform.workspace}"
}

resource "aws_iam_role" "lambda_exec" {
  name = local.function_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "editor" }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ssm_read" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        Resource = "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*"
      },
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = "arn:aws:kms:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda_exec.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  s3_bucket        = data.terraform_remote_state.bootstrap.outputs.lambda_artifacts_bucket
  s3_key           = var.zip_s3_key
  source_code_hash = var.zip_sha256
  timeout          = var.timeout
  memory_size      = var.memory_size
  architectures    = ["x86_64"]

  environment {
    variables = {
      ENV              = terraform.workspace
      LOG_LEVEL        = "INFO"
      LOG_JSON         = "true"
      OPENAI_MODEL     = var.openai_model
      SSM_PARAM_PREFIX = local.ssm_prefix
      LANGFUSE_HOST    = "https://cloud.langfuse.com"
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.ssm_read,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = { Project = "news-aggregator", Module = "editor" }
}
