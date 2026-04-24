# Shared assume-role policy for ECS tasks
data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- task execution role ---
# Pulls ECR images, writes CloudWatch logs, reads SSM SecureStrings.

resource "aws_iam_role" "task_execution" {
  name               = "scraper-task-execution-${terraform.workspace}"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = { Project = "news-aggregator", Module = "scraper" }
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_ssm" {
  statement {
    sid     = "ReadScraperSSMParams"
    actions = ["ssm:GetParameters"]
    resources = [
      "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter/news-aggregator/${terraform.workspace}/*",
    ]
  }

  statement {
    sid       = "DecryptSSMDefaultKey"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"]
  }
}

resource "aws_iam_role_policy" "task_execution_ssm" {
  name   = "ssm-read"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_ssm.json
}

# --- infrastructure role ---
# ECS Express uses this to manage its auto-provisioned ALB + TG + SG.

resource "aws_iam_role" "infrastructure" {
  name = "scraper-infrastructure-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ecs.amazonaws.com" }
    }]
  })

  tags = { Project = "news-aggregator", Module = "scraper" }
}

resource "aws_iam_role_policy_attachment" "infrastructure_managed" {
  role       = aws_iam_role.infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

# --- task role ---
# App-level permissions. Empty for #1; #2/#4 can attach perms later.

resource "aws_iam_role" "task" {
  name               = "scraper-task-${terraform.workspace}"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = { Project = "news-aggregator", Module = "scraper" }
}
