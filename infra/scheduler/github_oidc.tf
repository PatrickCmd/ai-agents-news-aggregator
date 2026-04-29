variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/name' form — gates the OIDC sub-claim."
  default     = "PatrickCmd/ai-agents-news-aggregator"
}

resource "aws_iam_role" "gh_actions_deploy" {
  name = "gh-actions-deploy-scheduler-${terraform.workspace}"

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

  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "gh_actions_deploy" {
  role = aws_iam_role.gh_actions_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Lambda artifact + tf-state (same as digest/editor/email)
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "arn:aws:s3:::news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}/scheduler/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}/scheduler/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
        Condition = {
          StringLike = { "s3:prefix" = ["scheduler/*", "scheduler"] }
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
        ]
        Resource = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-scheduler-${terraform.workspace}"
      },
      # IAM (lambda exec role + scheduler-also-has-sfn-role + this oidc role)
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
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-scheduler-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-cron-pipeline-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-remix-user-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-cron-eventbridge-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/gh-actions-deploy-scheduler-${terraform.workspace}",
        ]
      },
      # CloudWatch logs + alarms
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup", "logs:DeleteLogGroup",
          "logs:DescribeLogGroups", "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy", "logs:TagResource",
          "logs:UntagResource", "logs:ListTagsForResource",
        ]
        Resource = [
          "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/news-scheduler-${terraform.workspace}*",
          "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/vendedlogs/states/news-cron-pipeline-${terraform.workspace}*",
          "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/vendedlogs/states/news-remix-user-${terraform.workspace}*",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms",
          "cloudwatch:DescribeAlarms", "cloudwatch:ListTagsForResource",
          "cloudwatch:TagResource",
        ]
        Resource = [
          "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:news-scheduler-${terraform.workspace}-*",
          "arn:aws:cloudwatch:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alarm:news-cron-pipeline-${terraform.workspace}*",
        ]
      },
      # Step Functions state machines + EventBridge cron
      {
        Effect = "Allow"
        Action = [
          "states:CreateStateMachine", "states:UpdateStateMachine",
          "states:DeleteStateMachine", "states:DescribeStateMachine",
          "states:TagResource", "states:UntagResource",
          "states:ListTagsForResource",
        ]
        Resource = [
          "arn:aws:states:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:stateMachine:news-cron-pipeline-${terraform.workspace}",
          "arn:aws:states:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:stateMachine:news-remix-user-${terraform.workspace}",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "events:PutRule", "events:DeleteRule", "events:DescribeRule",
          "events:PutTargets", "events:RemoveTargets", "events:ListTargetsByRule",
          "events:TagResource", "events:UntagResource", "events:ListTagsForResource",
        ]
        Resource = "arn:aws:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:rule/news-cron-${terraform.workspace}*"
      },
      # EventBridge connections (Secrets Manager auto-created)
      {
        Effect = "Allow"
        Action = [
          "events:CreateConnection", "events:UpdateConnection",
          "events:DeleteConnection", "events:DescribeConnection",
        ]
        Resource = "arn:aws:events:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:connection/news-scraper-${terraform.workspace}/*"
      },
      # SSM
      {
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter/news-aggregator/${terraform.workspace}/*"
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
  description = "OIDC role ARN — paste into GitHub Environment vars as AWS_DEPLOY_ROLE_ARN_SCHEDULER."
}
