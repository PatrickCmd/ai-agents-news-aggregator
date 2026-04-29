variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/name' form — gates the OIDC sub-claim."
  default     = "PatrickCmd/ai-agents-news-aggregator"
}

resource "aws_iam_role" "gh_actions_deploy" {
  name = "gh-actions-deploy-api-${terraform.workspace}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Federated = data.aws_iam_openid_connect_provider.github.arn }
        Action    = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:environment:${terraform.workspace}"
          }
        }
      },
    ]
  })

  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_iam_role_policy" "gh_actions_deploy" {
  role = aws_iam_role.gh_actions_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Lambda artifact + tf-state
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "arn:aws:s3:::news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}/api/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}/api/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
        Condition = {
          StringLike = { "s3:prefix" = ["api/*", "api"] }
        }
      },
      # Lambda
      {
        Effect = "Allow"
        Action = [
          "lambda:GetFunction", "lambda:CreateFunction",
          "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
          "lambda:DeleteFunction", "lambda:TagResource",
          "lambda:UntagResource", "lambda:ListTags",
          "lambda:GetFunctionConfiguration",
          "lambda:AddPermission", "lambda:RemovePermission",
        ]
        Resource = "arn:aws:lambda:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:function:news-api-${terraform.workspace}"
      },
      # IAM
      {
        Effect = "Allow"
        Action = [
          "iam:GetRole", "iam:CreateRole", "iam:DeleteRole",
          "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole",
          "iam:ListRoleTags", "iam:GetRolePolicy", "iam:PutRolePolicy",
          "iam:DeleteRolePolicy", "iam:ListRolePolicies",
          "iam:AttachRolePolicy", "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies", "iam:PassRole",
        ]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-api-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/gh-actions-deploy-api-${terraform.workspace}",
        ]
      },
      # Logs + alarms
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup", "logs:DeleteLogGroup",
          "logs:DescribeLogGroups", "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy", "logs:TagResource",
          "logs:UntagResource", "logs:ListTagsForResource",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/news-api-${terraform.workspace}*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms",
          "cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource",
          "cloudwatch:TagResource",
        ]
        Resource = "arn:aws:cloudwatch:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:alarm:news-api-${terraform.workspace}*"
      },
      # API Gateway HTTP API
      {
        Effect = "Allow"
        Action = [
          "apigateway:GET", "apigateway:POST", "apigateway:PUT",
          "apigateway:PATCH", "apigateway:DELETE", "apigateway:TagResource",
          "apigateway:UntagResource",
        ]
        Resource = [
          "arn:aws:apigateway:${data.aws_region.current.name}::/apis",
          "arn:aws:apigateway:${data.aws_region.current.name}::/apis/*",
          "arn:aws:apigateway:${data.aws_region.current.name}::/tags/*",
        ]
      },
      # SSM
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/news-aggregator/${terraform.workspace}/*"
      },
      {
        Effect   = "Allow"
        Action   = "sts:GetCallerIdentity"
        Resource = "*"
      },
    ]
  })
}

output "gh_actions_role_arn" {
  value       = aws_iam_role.gh_actions_deploy.arn
  description = "OIDC role ARN — paste into GitHub Environment vars as AWS_DEPLOY_ROLE_ARN_API."
}
