resource "aws_apigatewayv2_api" "api" {
  name          = "news-api-${terraform.workspace}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins  = var.allowed_origins
    allow_methods  = ["GET", "PUT", "POST", "OPTIONS"]
    allow_headers  = ["Authorization", "Content-Type"]
    expose_headers = []
    max_age        = 3600
  }

  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/news-api-${terraform.workspace}"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      httpMethod     = "$context.httpMethod"
      path           = "$context.path"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
    })
  }

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_lambda_permission" "allow_api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "news-api-${terraform.workspace}-5xx"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "≥5 5XX responses from news-api in 5 min"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [data.aws_ssm_parameter.alerts_arn.value]

  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
    Stage = aws_apigatewayv2_stage.default.name
  }
}
