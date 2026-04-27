locals {
  function_name           = "news-api-${terraform.workspace}"
  ssm_prefix              = "/news-aggregator/${terraform.workspace}"
  lambda_artifacts_bucket = "news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}"
  remix_sfn_arn           = data.terraform_remote_state.scheduler.outputs.remix_state_machine_arn
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
  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "runtime" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = [
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}",
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = "arn:aws:kms:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"
      },
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = local.remix_sfn_arn
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda_exec.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  s3_bucket        = local.lambda_artifacts_bucket
  s3_key           = var.zip_s3_key
  source_code_hash = var.zip_sha256
  timeout          = var.timeout
  memory_size      = var.memory_size
  architectures    = ["x86_64"]

  environment {
    variables = {
      ENV                     = terraform.workspace
      LOG_LEVEL               = "INFO"
      LOG_JSON                = "true"
      SSM_PARAM_PREFIX        = local.ssm_prefix
      REMIX_STATE_MACHINE_ARN = local.remix_sfn_arn
      CLERK_ISSUER            = var.clerk_issuer
      CLERK_JWKS_URL          = "${var.clerk_issuer}/.well-known/jwks.json"
      ALLOWED_ORIGINS         = join(",", var.allowed_origins)
      GIT_SHA                 = var.git_sha
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.runtime,
    aws_cloudwatch_log_group.api,
  ]

  tags = { Project = "news-aggregator", Module = "api" }
}
