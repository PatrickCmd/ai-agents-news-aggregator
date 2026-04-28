variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/name' form — gates the OIDC sub-claim."
  default     = "PatrickCmd/ai-agents-news-aggregator"
}

resource "aws_iam_role" "gh_actions_deploy" {
  name = "gh-actions-deploy-digest-${terraform.workspace}"

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

  tags = { Project = "news-aggregator", Module = "digest" }
}

resource "aws_iam_role_policy" "gh_actions_deploy" {
  role = aws_iam_role.gh_actions_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Lambda artifact upload (services/agents/digest/deploy.py uploads to s3)
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "arn:aws:s3:::news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}/digest/*"
      },
      # Terraform state for digest module
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}/digest/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
        Condition = {
          StringLike = { "s3:prefix" = ["digest/*", "digest"] }
        }
      },
      # Lambda function management (terraform apply for the digest module)
      {
        Effect = "Allow"
        Action = [
          "lambda:GetFunction",
          "lambda:CreateFunction",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:DeleteFunction",
          "lambda:TagResource",
          "lambda:UntagResource",
          "lambda:ListTags",
          "lambda:GetFunctionConfiguration",
        ]
        Resource = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-digest-${terraform.workspace}"
      },
      # IAM for the lambda execution role + this OIDC role + policy attachments
      {
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:UpdateAssumeRolePolicy",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:ListRoleTags",
          "iam:GetRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:ListRolePolicies",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
          "iam:PassRole",
        ]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-digest-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/gh-actions-deploy-digest-${terraform.workspace}",
        ]
      },
      # CloudWatch Logs (log group is in this module)
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:DescribeLogGroups",
          "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy",
          "logs:TagResource",
          "logs:UntagResource",
          "logs:ListTagsForResource",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/news-digest-${terraform.workspace}*"
      },
      # CloudWatch alarms (this module's alarms.tf)
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm",
          "cloudwatch:DeleteAlarms",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:ListTagsForResource",
          "cloudwatch:TagResource",
        ]
        Resource = "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:news-digest-${terraform.workspace}-*"
      },
      # SSM read for SNS topic ARN lookup (alarms.tf reads /sns-alerts-arn)
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter/news-aggregator/${terraform.workspace}/*"
      },
      # STS GetCallerIdentity (Terraform always calls this on provider init)
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
  description = "OIDC role ARN — paste into GitHub Environment vars as AWS_DEPLOY_ROLE_ARN_DIGEST."
}
