variable "github_repo" {
  type        = string
  description = "GitHub repo in 'owner/name' form — gates the OIDC sub-claim."
  default     = "PatrickCmd/ai-agents-news-aggregator"
}

resource "aws_iam_role" "gh_actions_deploy" {
  name = "gh-actions-deploy-scraper-${terraform.workspace}"

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

  tags = { Project = "news-aggregator", Module = "scraper" }
}

resource "aws_iam_role_policy" "gh_actions_deploy" {
  role = aws_iam_role.gh_actions_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Terraform state
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}/scraper/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
        Condition = {
          StringLike = { "s3:prefix" = ["scraper/*", "scraper"] }
        }
      },
      # ECR — scraper docker image push
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage", "ecr:PutImage",
          "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload", "ecr:DescribeRepositories",
          "ecr:DescribeImages", "ecr:ListImages",
          "ecr:CreateRepository", "ecr:DeleteRepository",
          "ecr:PutLifecyclePolicy", "ecr:GetLifecyclePolicy",
          "ecr:TagResource", "ecr:UntagResource", "ecr:ListTagsForResource",
        ]
        Resource = "arn:aws:ecr:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:repository/news-scraper-${terraform.workspace}"
      },
      # ECS service update
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService", "ecs:DescribeServices", "ecs:DescribeTaskDefinition",
          "ecs:RegisterTaskDefinition", "ecs:DeregisterTaskDefinition",
          "ecs:ListTasks", "ecs:DescribeTasks",
          "ecs:CreateService", "ecs:DeleteService",
          "ecs:CreateCluster", "ecs:DeleteCluster", "ecs:DescribeClusters",
          "ecs:TagResource", "ecs:UntagResource", "ecs:ListTagsForResource",
        ]
        Resource = "*"
      },
      # IAM (task role + execution role + this oidc role)
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
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-scraper-task-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/news-scraper-execution-${terraform.workspace}",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/gh-actions-deploy-scraper-${terraform.workspace}",
        ]
      },
      # CloudWatch logs (ECS task log group)
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup", "logs:DeleteLogGroup",
          "logs:DescribeLogGroups", "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy", "logs:TagResource",
          "logs:UntagResource", "logs:ListTagsForResource",
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/news-scraper-${terraform.workspace}*"
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
  description = "OIDC role ARN — paste into GitHub Environment vars as AWS_DEPLOY_ROLE_ARN."
}
