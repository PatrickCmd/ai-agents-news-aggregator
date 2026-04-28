resource "aws_iam_role" "gh_actions_deploy" {
  name = "gh-actions-deploy-web-${terraform.workspace}"

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
            # Restrict to the repo + the matching GitHub Environment.
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:environment:${terraform.workspace}"
          }
        }
      },
    ]
  })

  tags = { Project = "news-aggregator", Module = "web" }
}

resource "aws_iam_role_policy" "gh_actions_deploy" {
  role = aws_iam_role.gh_actions_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.assets.arn,
          "${aws_s3_bucket.assets.arn}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "cloudfront:CreateInvalidation"
        Resource = aws_cloudfront_distribution.web.arn
      },
    ]
  })
}
