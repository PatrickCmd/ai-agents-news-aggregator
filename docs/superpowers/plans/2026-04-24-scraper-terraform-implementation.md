# Scraper Terraform IaC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Terraform modules to deploy `services/scraper` to AWS as an ECS Express Mode service on `scraper.patrickcmd.dev`, establish the per-sub-project infra convention (`infra/<name>/`), and wire `deploy.py` to the resulting infra.

**Architecture:** Two Terraform root modules — `infra/bootstrap/` (S3+DynamoDB remote state, local state only, run once) and `infra/scraper/` (ECR, ECS cluster, IAM roles, SSM SecureString params, ACM cert, Route53 records, ECS Express service, CPU-tracking autoscaling). Secrets never touch Terraform state; `sync_secrets.py` pushes `.env` values to SSM via the AWS CLI.

**Tech Stack:** Terraform ≥ 1.5 / AWS Provider `~> 5.80` / AWS CLI (profile `aiengineer`) / Python + boto3 (sync_secrets, deploy.py).

**Design spec:** [docs/superpowers/specs/2026-04-24-scraper-terraform-design.md](../specs/2026-04-24-scraper-terraform-design.md)

---

## Working conventions

- Branch: `sub-project#1` (continuing from Ingestion work).
- **Terraform doesn't follow pytest TDD.** Validation cycle per task: write config → `terraform fmt` → `terraform validate` → `terraform plan` (assert resource count/shape) → commit. Apply happens at phase boundaries where noted.
- Python components (`sync_secrets.py`, `deploy.py` updates) use the repo's existing TDD flow (unit tests with pytest).
- After every green task, commit. Conventional Commits (`feat(infra): ...`, `chore(deploy): ...`, etc.).
- **Definition of done for the overall plan:** `terraform apply` clean on both modules, `https://scraper.patrickcmd.dev/healthz` returns 200 with matching `git_sha`, `make scraper-deploy` end-to-end green.

---

## Phase 1 — `infra/bootstrap/` (one-time state backend)

### Task 1.1: Create bootstrap Terraform module

**Files:**
- Create: `infra/bootstrap/main.tf`
- Create: `infra/bootstrap/variables.tf`
- Create: `infra/bootstrap/outputs.tf`
- Create: `infra/bootstrap/.gitignore`

- [ ] **Step 1: Delete the placeholder `.gitkeep`**

```bash
git rm infra/.gitkeep
```

- [ ] **Step 2: Create `infra/bootstrap/main.tf`**

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
  # No backend block -> local state. This is intentional (chicken-and-egg).
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

data "aws_caller_identity" "current" {}

locals {
  state_bucket_name = "news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
  lock_table_name   = "news-aggregator-tf-locks"
}

resource "aws_s3_bucket" "tf_state" {
  bucket = local.state_bucket_name

  tags = {
    Project = "news-aggregator"
    Purpose = "terraform-state"
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    noncurrent_version_expiration { noncurrent_days = 90 }
  }
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = local.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Project = "news-aggregator"
    Purpose = "terraform-lock"
  }
}
```

- [ ] **Step 3: Create `infra/bootstrap/variables.tf`**

```hcl
variable "aws_region" {
  description = "AWS region for state bucket + lock table"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile to use"
  type        = string
  default     = "aiengineer"
}
```

- [ ] **Step 4: Create `infra/bootstrap/outputs.tf`**

```hcl
output "state_bucket_name" {
  description = "Name of the S3 bucket holding Terraform state for all modules"
  value       = aws_s3_bucket.tf_state.bucket
}

output "lock_table_name" {
  description = "Name of the DynamoDB table used for state locking"
  value       = aws_dynamodb_table.tf_lock.name
}

output "region" {
  description = "AWS region"
  value       = var.aws_region
}

output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}
```

- [ ] **Step 5: Create `infra/bootstrap/.gitignore`**

```gitignore
.terraform/
.terraform.lock.hcl
*.tfstate
*.tfstate.backup
*.tfvars
crash.log
crash.*.log
```

> Note: `.terraform.lock.hcl` is intentionally gitignored for bootstrap (local, single-developer). For the scraper module, we'll commit it.

- [ ] **Step 6: Validate**

```bash
cd infra/bootstrap
terraform init
terraform fmt -check
terraform validate
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 7: Plan**

```bash
terraform plan
```

Expected: Shows `Plan: 6 to add, 0 to change, 0 to destroy.` Resources: `aws_s3_bucket.tf_state`, `aws_s3_bucket_versioning.tf_state`, `aws_s3_bucket_server_side_encryption_configuration.tf_state`, `aws_s3_bucket_public_access_block.tf_state`, `aws_s3_bucket_lifecycle_configuration.tf_state`, `aws_dynamodb_table.tf_lock`.

- [ ] **Step 8: Commit**

```bash
cd ../..
git add infra/.gitkeep infra/bootstrap/main.tf infra/bootstrap/variables.tf \
        infra/bootstrap/outputs.tf infra/bootstrap/.gitignore
git commit -m "feat(infra): add bootstrap module for Terraform state backend"
```

---

### Task 1.2: Apply bootstrap + capture outputs

**Files:** (no code changes; infra apply)

- [ ] **Step 1: Apply**

```bash
cd infra/bootstrap
terraform apply
```

Expected: prompts for confirmation, then `Apply complete! Resources: 6 added, 0 changed, 0 destroyed.`

- [ ] **Step 2: Verify outputs**

```bash
terraform output
```

Expected output (values will differ):

```
account_id        = "1234567890"
lock_table_name   = "news-aggregator-tf-locks"
region            = "us-east-1"
state_bucket_name = "news-aggregator-tf-state-1234567890"
```

**Record these values** — the scraper module needs them as `-backend-config` inputs.

- [ ] **Step 3: Verify AWS-side**

```bash
aws s3 ls --profile aiengineer | grep news-aggregator-tf-state
aws dynamodb describe-table --table-name news-aggregator-tf-locks --profile aiengineer \
  --query 'Table.{Status:TableStatus,BillingMode:BillingModeSummary.BillingMode}'
```

Expected: bucket exists; DynamoDB table status `ACTIVE`, billing `PAY_PER_REQUEST`.

- [ ] **Step 4: Return to repo root** (no commit — this is a cloud-state change, not a code change)

```bash
cd ../..
```

---

## Phase 2 — `infra/scraper/` scaffold

### Task 2.1: Provider + backend + variables + data sources

**Files:**
- Create: `infra/scraper/backend.tf`
- Create: `infra/scraper/variables.tf`
- Create: `infra/scraper/data.tf`
- Create: `infra/scraper/.gitignore`
- Create: `infra/scraper/terraform.tfvars.example`

- [ ] **Step 1: Create `infra/scraper/backend.tf`**

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  backend "s3" {
    # Values provided via -backend-config at init time.
    # bucket         = "news-aggregator-tf-state-<account>"
    # key            = "scraper/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "news-aggregator-tf-locks"
    encrypt = true
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}
```

- [ ] **Step 2: Create `infra/scraper/variables.tf`**

```hcl
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS CLI profile"
  type        = string
  default     = "aiengineer"
}

variable "domain_name" {
  description = "Root Route53 zone (no trailing dot)"
  type        = string
  default     = "patrickcmd.dev"
}

variable "scraper_subdomain" {
  description = "Subdomain label for the scraper (scraper -> scraper.<domain>)"
  type        = string
  default     = "scraper"
}

variable "cluster_name" {
  description = "ECS cluster name (shared across sub-projects)"
  type        = string
  default     = "news-aggregator"
}

variable "ecr_repo_name" {
  description = "ECR repository for the scraper image"
  type        = string
  default     = "news-scraper"
}

variable "image_tag" {
  description = "ECR image tag to deploy. Overridden by deploy.py with git SHA."
  type        = string
  default     = "latest"
}

variable "task_cpu" {
  description = "Fargate task vCPU units (256/512/1024/2048/4096)"
  type        = number
  default     = 2048
}

variable "task_memory" {
  description = "Fargate task memory in MiB"
  type        = number
  default     = 4096
}

variable "min_capacity" {
  description = "Min number of ECS tasks"
  type        = number
  default     = 0
}

variable "max_capacity" {
  description = "Max number of ECS tasks"
  type        = number
  default     = 2
}

variable "scale_in_cooldown_seconds" {
  description = "Scale-in cooldown, protects long-running background tasks"
  type        = number
  default     = 1800
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention"
  type        = number
  default     = 14
}

variable "vpc_id" {
  description = "VPC ID for the service. Null = use default VPC."
  type        = string
  default     = null
}

variable "subnet_ids" {
  description = "Subnet IDs for the service. Null = use default VPC subnets."
  type        = list(string)
  default     = null
}
```

- [ ] **Step 3: Create `infra/scraper/data.tf`**

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_vpc" "target" {
  default = var.vpc_id == null
  id      = var.vpc_id
}

data "aws_subnets" "default_vpc" {
  count = var.subnet_ids == null ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.target.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_route53_zone" "main" {
  name         = "${var.domain_name}."
  private_zone = false
}

locals {
  resolved_subnet_ids = (
    var.subnet_ids != null
    ? var.subnet_ids
    : data.aws_subnets.default_vpc[0].ids
  )
}
```

- [ ] **Step 4: Create `infra/scraper/.gitignore`**

```gitignore
.terraform/
*.tfstate
*.tfstate.backup
terraform.tfvars
crash.log
crash.*.log
```

> Note: `.terraform.lock.hcl` IS committed for the scraper module (reproducible provider versions across env).

- [ ] **Step 5: Create `infra/scraper/terraform.tfvars.example`**

```hcl
# Copy to terraform.tfvars and fill in; terraform.tfvars is gitignored.
# Most values default to sensible prod-ready choices — only override what you need.

# aws_region       = "us-east-1"
# aws_profile      = "aiengineer"
# domain_name      = "patrickcmd.dev"
# image_tag        = "latest"  # overridden by deploy.py with git SHA
```

- [ ] **Step 6: Initialize the remote backend**

```bash
cd infra/scraper

# Replace <ACCOUNT> with the account_id from bootstrap output (Task 1.2, Step 2).
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-<ACCOUNT>" \
  -backend-config="key=scraper/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=news-aggregator-tf-locks"
```

Expected: `Terraform has been successfully initialized!` — and a new `.terraform.lock.hcl` appears.

- [ ] **Step 7: Create the `dev` workspace**

```bash
terraform workspace new dev
```

Expected: `Created and switched to workspace "dev"!`

- [ ] **Step 8: Validate + plan (should be empty)**

```bash
terraform fmt -check
terraform validate
terraform plan
```

Expected: validate passes; plan shows `No changes. Your infrastructure matches the configuration.`

- [ ] **Step 9: Commit**

```bash
cd ../..
git add infra/scraper/backend.tf infra/scraper/variables.tf infra/scraper/data.tf \
        infra/scraper/.gitignore infra/scraper/terraform.tfvars.example \
        infra/scraper/.terraform.lock.hcl
git commit -m "feat(infra): add scraper Terraform scaffold (backend, variables, data sources)"
```

---

## Phase 3 — ECR, cluster, logs, IAM roles, SSM

### Task 3.1: ECR repository + lifecycle policy

**Files:**
- Create: `infra/scraper/ecr.tf`

- [ ] **Step 1: Create `infra/scraper/ecr.tf`**

```hcl
resource "aws_ecr_repository" "scraper" {
  name                 = var.ecr_repo_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}

resource "aws_ecr_lifecycle_policy" "scraper" {
  repository = aws_ecr_repository.scraper.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
```

- [ ] **Step 2: Plan**

```bash
cd infra/scraper
terraform fmt -check
terraform validate
terraform plan
```

Expected: `Plan: 2 to add, 0 to change, 0 to destroy.` (aws_ecr_repository, aws_ecr_lifecycle_policy)

- [ ] **Step 3: Commit** (no apply yet — batch apply at end of phase 3)

```bash
cd ../..
git add infra/scraper/ecr.tf
git commit -m "feat(infra): scraper ECR repo with lifecycle policy (keep last 10 images)"
```

---

### Task 3.2: ECS cluster + CloudWatch log group

**Files:**
- Create: `infra/scraper/cluster.tf`

- [ ] **Step 1: Create `infra/scraper/cluster.tf`**

```hcl
resource "aws_ecs_cluster" "main" {
  name = var.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Project = "news-aggregator"
  }
}

resource "aws_cloudwatch_log_group" "scraper" {
  name              = "/ecs/${var.ecr_repo_name}"
  retention_in_days = var.log_retention_days

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}
```

- [ ] **Step 2: Plan**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 4 to add, 0 to change, 0 to destroy.` (previous 2 + cluster + log group)

- [ ] **Step 3: Commit**

```bash
cd ../..
git add infra/scraper/cluster.tf
git commit -m "feat(infra): scraper ECS cluster + CloudWatch log group"
```

---

### Task 3.3: IAM — task execution role

**Files:**
- Create: `infra/scraper/iam.tf`

- [ ] **Step 1: Create `infra/scraper/iam.tf`** (first pass — just task_execution)

```hcl
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
      "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/news-aggregator/${terraform.workspace}/*",
    ]
  }

  statement {
    sid       = "DecryptSSMDefaultKey"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"]
  }
}

resource "aws_iam_role_policy" "task_execution_ssm" {
  name   = "ssm-read"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_ssm.json
}
```

- [ ] **Step 2: Plan**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 7 to add, 0 to change, 0 to destroy.` (previous 4 + role + managed attach + inline policy)

- [ ] **Step 3: Commit**

```bash
cd ../..
git add infra/scraper/iam.tf
git commit -m "feat(infra): scraper task-execution IAM role with SSM read perms"
```

---

### Task 3.4: IAM — infrastructure role + task role

**Files:**
- Modify: `infra/scraper/iam.tf`

> **Verification step needed:** the ECS Express infrastructure role needs an AWS-managed policy or an inline one covering ALB/TG/SG management. Check the current state of AWS docs at [the Express service overview page](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html). If AWS provides a managed policy (commonly named like `AmazonECSInfrastructureRolePolicyForExpressService`), attach it. Otherwise, use the inline fallback below.

- [ ] **Step 1: Append to `infra/scraper/iam.tf`**

```hcl
# --- infrastructure role ---
# ECS Express uses this to auto-manage ALB, target groups, SGs on your behalf.

resource "aws_iam_role" "infrastructure" {
  name               = "scraper-infrastructure-${terraform.workspace}"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = { Project = "news-aggregator", Module = "scraper" }
}

# Inline fallback policy. Replace with a managed attach if AWS provides one.
# Grants the permissions documented at
# https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html
data "aws_iam_policy_document" "infrastructure" {
  statement {
    sid    = "ManageLoadBalancing"
    effect = "Allow"
    actions = [
      "elasticloadbalancing:CreateLoadBalancer",
      "elasticloadbalancing:CreateTargetGroup",
      "elasticloadbalancing:CreateListener",
      "elasticloadbalancing:DeleteLoadBalancer",
      "elasticloadbalancing:DeleteTargetGroup",
      "elasticloadbalancing:DeleteListener",
      "elasticloadbalancing:ModifyLoadBalancerAttributes",
      "elasticloadbalancing:ModifyTargetGroup",
      "elasticloadbalancing:ModifyTargetGroupAttributes",
      "elasticloadbalancing:ModifyListener",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeListeners",
      "elasticloadbalancing:DescribeTargetHealth",
      "elasticloadbalancing:RegisterTargets",
      "elasticloadbalancing:DeregisterTargets",
      "elasticloadbalancing:AddTags",
      "elasticloadbalancing:RemoveTags",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageNetworking"
    effect = "Allow"
    actions = [
      "ec2:CreateSecurityGroup",
      "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupIngress",
      "ec2:RevokeSecurityGroupEgress",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:CreateTags",
      "ec2:DeleteTags",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "infrastructure" {
  name   = "manage-infra"
  role   = aws_iam_role.infrastructure.id
  policy = data.aws_iam_policy_document.infrastructure.json
}

# --- task role ---
# App-level permissions. Empty for #1; #2/#4 can attach perms later.

resource "aws_iam_role" "task" {
  name               = "scraper-task-${terraform.workspace}"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = { Project = "news-aggregator", Module = "scraper" }
}
```

- [ ] **Step 2: Verify whether a managed infrastructure policy exists now**

Run:

```bash
aws iam list-policies --scope AWS --query 'Policies[?contains(PolicyName, `ECSInfrastructure`)].[PolicyName,Arn]' \
  --profile aiengineer --output table
```

If a managed policy appears (e.g., `AmazonECSInfrastructureRolePolicy`), replace the inline `aws_iam_role_policy.infrastructure` + `data.aws_iam_policy_document.infrastructure` with:

```hcl
resource "aws_iam_role_policy_attachment" "infrastructure_managed" {
  role       = aws_iam_role.infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/<policy-name-from-command>"
}
```

If no managed policy exists, keep the inline policy as-is.

- [ ] **Step 3: Plan**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 10 to add, 0 to change, 0 to destroy.` (previous 7 + infrastructure role + inline policy + task role).

- [ ] **Step 4: Commit**

```bash
cd ../..
git add infra/scraper/iam.tf
git commit -m "feat(infra): scraper infrastructure + task IAM roles"
```

---

### Task 3.5: SSM SecureString parameters (8 of them)

**Files:**
- Create: `infra/scraper/ssm.tf`

- [ ] **Step 1: Create `infra/scraper/ssm.tf`**

```hcl
locals {
  sensitive_env = [
    "supabase_db_url",
    "supabase_pooler_url",
    "openai_api_key",
    "langfuse_public_key",
    "langfuse_secret_key",
    "youtube_proxy_username",
    "youtube_proxy_password",
    "resend_api_key",
  ]
}

resource "aws_ssm_parameter" "sensitive" {
  for_each = toset(local.sensitive_env)

  name        = "/news-aggregator/${terraform.workspace}/${each.value}"
  description = "Sensitive env for the scraper service (${terraform.workspace})"
  type        = "SecureString"
  value       = "placeholder-set-via-sync-secrets"  # pragma: allowlist secret

  lifecycle {
    # Real values are pushed by infra/scraper/sync_secrets.py — never Terraform-managed.
    ignore_changes = [value]
  }

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}
```

- [ ] **Step 2: Plan**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 18 to add, 0 to change, 0 to destroy.` (previous 10 + 8 SSM params)

- [ ] **Step 3: Commit**

```bash
cd ../..
git add infra/scraper/ssm.tf
git commit -m "feat(infra): scraper SSM SecureString parameters (placeholder values)"
```

---

### Task 3.6: Apply phase 3 + verify AWS-side

**Files:** (no code changes; infra apply)

- [ ] **Step 1: Apply**

```bash
cd infra/scraper
terraform apply
```

Expected: `Apply complete! Resources: 18 added, 0 changed, 0 destroyed.`

- [ ] **Step 2: Verify**

```bash
aws ecr describe-repositories --repository-names news-scraper --profile aiengineer \
  --query 'repositories[0].repositoryUri'

aws ecs describe-clusters --clusters news-aggregator --profile aiengineer \
  --query 'clusters[0].status'

aws logs describe-log-groups --log-group-name-prefix /ecs/news-scraper \
  --profile aiengineer --query 'logGroups[0].retentionInDays'

aws iam get-role --role-name scraper-task-execution-dev --profile aiengineer \
  --query 'Role.Arn'

aws ssm describe-parameters --parameter-filters 'Key=Name,Option=BeginsWith,Values=/news-aggregator/dev/' \
  --profile aiengineer --query 'Parameters[].Name' --output table
```

Expected: repo URI like `<account>.dkr.ecr.us-east-1.amazonaws.com/news-scraper`; cluster status `ACTIVE`; retention `14`; role ARN returned; 8 SSM param names listed.

- [ ] **Step 3: Return to repo root** (no commit — cloud-state change)

```bash
cd ../..
```

---

## Phase 4 — ACM certificate + Route53

### Task 4.1: ACM certificate + validation records

**Files:**
- Create: `infra/scraper/dns.tf`

- [ ] **Step 1: Create `infra/scraper/dns.tf`**

```hcl
resource "aws_acm_certificate" "scraper" {
  domain_name       = "${var.scraper_subdomain}.${var.domain_name}"
  validation_method = "DNS"

  lifecycle { create_before_destroy = true }

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}

resource "aws_route53_record" "scraper_validation" {
  for_each = {
    for dvo in aws_acm_certificate.scraper.domain_validation_options :
    dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = data.aws_route53_zone.main.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "scraper" {
  certificate_arn         = aws_acm_certificate.scraper.arn
  validation_record_fqdns = [for r in aws_route53_record.scraper_validation : r.fqdn]
}
```

> The `aws_route53_record.scraper_alias` (A-record pointing at the ALB) is added in Phase 5 once the service is defined.

- [ ] **Step 2: Plan + apply**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 3 to add, 0 to change, 0 to destroy.` (cert, validation CNAME, cert_validation)

```bash
terraform apply
```

Expected: apply completes; validation may take 1–5 minutes as DNS propagates.

- [ ] **Step 3: Verify**

```bash
aws acm list-certificates --profile aiengineer \
  --query 'CertificateSummaryList[?DomainName==`scraper.patrickcmd.dev`].[Status,CertificateArn]' \
  --output table
```

Expected: Status `ISSUED`.

- [ ] **Step 4: Commit**

```bash
cd ../..
git add infra/scraper/dns.tf
git commit -m "feat(infra): ACM cert + Route53 validation for scraper.patrickcmd.dev"
```

---

## Phase 5 — ECS Express service + autoscaling

### Task 5.1: Push a `:latest` image first

**Files:** (no code changes; image push)

The service resource references `${ecr_repo_url}:${image_tag}`. ECS will fail to launch if the image doesn't exist. Push a `:latest` image first.

- [ ] **Step 1: Build and push the current HEAD as `:latest`**

```bash
uv run python services/scraper/deploy.py --mode build
```

Expected: Docker build (~5–10 min for Chromium layer), ECR push of `:<sha>` and `:latest` tags.

- [ ] **Step 2: Verify in ECR**

```bash
aws ecr list-images --repository-name news-scraper --profile aiengineer \
  --query 'imageIds[?imageTag==`latest`].imageTag'
```

Expected: `["latest"]`.

- [ ] **Step 3: No commit** — this is a cloud-side artifact.

---

### Task 5.2: ECS Express service

**Files:**
- Create: `infra/scraper/service.tf`

- [ ] **Step 1: Create `infra/scraper/service.tf`**

```hcl
resource "aws_ecs_express_gateway_service" "scraper" {
  service_name            = "scraper"
  cluster                 = aws_ecs_cluster.main.name
  execution_role_arn      = aws_iam_role.task_execution.arn
  infrastructure_role_arn = aws_iam_role.infrastructure.arn
  task_role_arn           = aws_iam_role.task.arn
  cpu                     = tostring(var.task_cpu)
  memory                  = tostring(var.task_memory)
  health_check_path       = "/healthz"
  wait_for_steady_state   = true

  primary_container {
    image          = "${aws_ecr_repository.scraper.repository_url}:${var.image_tag}"
    container_port = 8000

    aws_logs_configuration {
      log_group = aws_cloudwatch_log_group.scraper.name
    }

    # Non-sensitive config
    environment {
      name  = "ENV"
      value = terraform.workspace
    }
    environment {
      name  = "LOG_LEVEL"
      value = "INFO"
    }
    environment {
      name  = "LOG_JSON"
      value = "true"
    }
    environment {
      name  = "OPENAI_MODEL"
      value = "gpt-5.4-mini"
    }
    environment {
      name  = "RSS_MCP_PATH"
      value = "/app/rss-mcp/dist/index.js"
    }
    environment {
      name  = "WEB_SEARCH_MAX_TURNS"
      value = "15"
    }
    environment {
      name  = "WEB_SEARCH_SITE_TIMEOUT"
      value = "120"
    }
    environment {
      name  = "YOUTUBE_TRANSCRIPT_CONCURRENCY"
      value = "3"
    }
    environment {
      name  = "RSS_FEED_CONCURRENCY"
      value = "5"
    }
    environment {
      name  = "WEB_SEARCH_SITE_CONCURRENCY"
      value = "2"
    }
    environment {
      name  = "YOUTUBE_PROXY_ENABLED"
      value = "true"
    }
    environment {
      name  = "LANGFUSE_HOST"
      value = "https://cloud.langfuse.com"
    }

    # Sensitive config via SSM SecureString
    secret {
      name       = "SUPABASE_DB_URL"
      value_from = aws_ssm_parameter.sensitive["supabase_db_url"].arn
    }
    secret {
      name       = "SUPABASE_POOLER_URL"
      value_from = aws_ssm_parameter.sensitive["supabase_pooler_url"].arn
    }
    secret {
      name       = "OPENAI_API_KEY"
      value_from = aws_ssm_parameter.sensitive["openai_api_key"].arn
    }
    secret {
      name       = "LANGFUSE_PUBLIC_KEY"
      value_from = aws_ssm_parameter.sensitive["langfuse_public_key"].arn
    }
    secret {
      name       = "LANGFUSE_SECRET_KEY"
      value_from = aws_ssm_parameter.sensitive["langfuse_secret_key"].arn
    }
    secret {
      name       = "YOUTUBE_PROXY_USERNAME"
      value_from = aws_ssm_parameter.sensitive["youtube_proxy_username"].arn
    }
    secret {
      name       = "YOUTUBE_PROXY_PASSWORD"
      value_from = aws_ssm_parameter.sensitive["youtube_proxy_password"].arn
    }
    secret {
      name       = "RESEND_API_KEY"
      value_from = aws_ssm_parameter.sensitive["resend_api_key"].arn
    }
  }

  network_configuration {
    subnets         = local.resolved_subnet_ids
    security_groups = []
  }

  listener_configuration {
    protocol        = "HTTPS"
    certificate_arn = aws_acm_certificate_validation.scraper.certificate_arn
  }

  depends_on = [aws_ssm_parameter.sensitive]

  tags = {
    Project = "news-aggregator"
    Module  = "scraper"
  }
}
```

- [ ] **Step 2: Plan (should NOT apply yet — secrets are placeholders)**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 1 to add, 0 to change, 0 to destroy.` (just the service).

- [ ] **Step 3: Commit**

```bash
cd ../..
git add infra/scraper/service.tf
git commit -m "feat(infra): scraper ECS Express service definition"
```

---

### Task 5.3: Add Route53 A-alias record

**Files:**
- Modify: `infra/scraper/dns.tf`

- [ ] **Step 1: Append to `infra/scraper/dns.tf`**

```hcl
resource "aws_route53_record" "scraper_alias" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "${var.scraper_subdomain}.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_ecs_express_gateway_service.scraper.alb_dns_name
    zone_id                = aws_ecs_express_gateway_service.scraper.alb_zone_id
    evaluate_target_health = true
  }
}
```

> **Attribute-name verification:** if `aws_ecs_express_gateway_service.scraper.alb_dns_name` raises an unknown-attribute error at `terraform plan`, fall back to a data-source lookup by tag:
>
> ```hcl
> data "aws_lb" "scraper" {
>   tags = { "ecs:express:service" = aws_ecs_express_gateway_service.scraper.service_name }
>   depends_on = [aws_ecs_express_gateway_service.scraper]
> }
>
> # ...then use data.aws_lb.scraper.dns_name / zone_id
> ```

- [ ] **Step 2: Plan**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 2 to add, 0 to change, 0 to destroy.` (service + A-record).

- [ ] **Step 3: Commit**

```bash
cd ../..
git add infra/scraper/dns.tf
git commit -m "feat(infra): Route53 A-alias for scraper.patrickcmd.dev -> ALB"
```

---

### Task 5.4: Auto-scaling + outputs

**Files:**
- Create: `infra/scraper/autoscaling.tf`
- Create: `infra/scraper/outputs.tf`

- [ ] **Step 1: Create `infra/scraper/autoscaling.tf`**

```hcl
resource "aws_appautoscaling_target" "scraper" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_express_gateway_service.scraper.service_name}"
  min_capacity       = var.min_capacity
  max_capacity       = var.max_capacity
}

resource "aws_appautoscaling_policy" "scraper_cpu" {
  name               = "scraper-cpu-tracking-${terraform.workspace}"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.scraper.resource_id
  scalable_dimension = aws_appautoscaling_target.scraper.scalable_dimension
  service_namespace  = aws_appautoscaling_target.scraper.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = var.scale_in_cooldown_seconds
    scale_out_cooldown = 60
  }
}
```

- [ ] **Step 2: Create `infra/scraper/outputs.tf`**

```hcl
output "scraper_url" {
  description = "Public HTTPS URL for the scraper"
  value       = "https://${var.scraper_subdomain}.${var.domain_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name (for debugging; prefer scraper_url)"
  value       = aws_ecs_express_gateway_service.scraper.alb_dns_name
}

output "ecr_repo_url" {
  description = "ECR repository URL for pushing images"
  value       = aws_ecr_repository.scraper.repository_url
}

output "log_group_name" {
  description = "CloudWatch log group for scraper tasks"
  value       = aws_cloudwatch_log_group.scraper.name
}

output "environment" {
  description = "Terraform workspace (env) this deploy targets"
  value       = terraform.workspace
}
```

- [ ] **Step 3: Plan**

```bash
cd infra/scraper
terraform validate
terraform plan
```

Expected: `Plan: 4 to add, 0 to change, 0 to destroy.` (service + A-record + autoscaling target + autoscaling policy)

- [ ] **Step 4: Commit**

```bash
cd ../..
git add infra/scraper/autoscaling.tf infra/scraper/outputs.tf
git commit -m "feat(infra): scraper CPU-based autoscaling + module outputs"
```

---

### Task 5.5: Apply Phase 5 + verify live

**Files:** (no code changes; infra apply)

- [ ] **Step 1: Push real secrets to SSM** (see next task for sync_secrets.py; for this smoke we'll do it manually first)

```bash
# Replace each <VALUE> with the real value from .env
aws ssm put-parameter --name /news-aggregator/dev/supabase_db_url       --type SecureString --overwrite --value '<SUPABASE_DB_URL>'       --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/supabase_pooler_url   --type SecureString --overwrite --value '<SUPABASE_POOLER_URL>'   --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/openai_api_key        --type SecureString --overwrite --value '<OPENAI_API_KEY>'        --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/langfuse_public_key   --type SecureString --overwrite --value '<LANGFUSE_PUBLIC_KEY>'   --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/langfuse_secret_key   --type SecureString --overwrite --value '<LANGFUSE_SECRET_KEY>'   --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/youtube_proxy_username --type SecureString --overwrite --value '<YT_USER>'              --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/youtube_proxy_password --type SecureString --overwrite --value '<YT_PASS>'              --profile aiengineer
aws ssm put-parameter --name /news-aggregator/dev/resend_api_key         --type SecureString --overwrite --value '<RESEND_API_KEY>'       --profile aiengineer
```

(Task 6.1 replaces this with `make secrets-sync`.)

- [ ] **Step 2: Apply**

```bash
cd infra/scraper
terraform apply
```

Expected: `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.` The apply may take 2–3 minutes for the ALB to provision; `wait_for_steady_state=true` blocks until tasks are healthy.

- [ ] **Step 3: Smoke-test the endpoint**

```bash
curl -s https://scraper.patrickcmd.dev/healthz
```

Expected: `{"status":"ok","git_sha":"<hash>"}`.

- [ ] **Step 4: Trigger a minimal RSS-only ingest**

```bash
curl -s -X POST https://scraper.patrickcmd.dev/ingest/rss \
  -H 'content-type: application/json' \
  -d '{"lookback_hours":3}' | jq .
```

Expected: 202 response with `{"id":"<uuid>","status":"running",...}`.

Poll:

```bash
curl -s https://scraper.patrickcmd.dev/runs | jq '.[0].status'
```

Within 1–2 minutes expect `"success"` or `"partial"` depending on feed availability.

- [ ] **Step 5: Return to repo root** (no commit — cloud-state change)

```bash
cd ../..
```

---

## Phase 6 — Glue: sync_secrets.py, deploy.py, Makefile, docs

### Task 6.1: `sync_secrets.py`

**Files:**
- Create: `infra/scraper/sync_secrets.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_sync_secrets.py`

> Note: the test file lives inside the scraper's test tree rather than a new infra test directory, so it's picked up by the existing `pytest` testpaths.

- [ ] **Step 1: Write failing unit test**

Create `services/scraper/src/news_scraper/tests/unit/test_sync_secrets.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# The script lives outside the news_scraper package (in infra/), so load it manually.
_SCRIPT = (
    Path(__file__).resolve().parents[6]
    / "infra"
    / "scraper"
    / "sync_secrets.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_secrets", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_secrets"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_env_to_param_map_covers_8_secrets() -> None:
    mod = _load_module()
    assert len(mod.ENV_TO_PARAM) == 8
    assert "SUPABASE_DB_URL" in mod.ENV_TO_PARAM
    assert "OPENAI_API_KEY" in mod.ENV_TO_PARAM
    assert mod.ENV_TO_PARAM["SUPABASE_DB_URL"] == "supabase_db_url"


def test_push_params_calls_put_parameter_for_each_set_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()

    # Set only 3 of 8 env vars
    for key in list(mod.ENV_TO_PARAM.keys()):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")  # pragma: allowlist secret
    monkeypatch.setenv("RESEND_API_KEY", "re_fake")  # pragma: allowlist secret

    fake_ssm = MagicMock()
    count = mod.push_params(fake_ssm, env="dev")

    assert count == 3
    assert fake_ssm.put_parameter.call_count == 3
    names = {call.kwargs["Name"] for call in fake_ssm.put_parameter.call_args_list}
    assert names == {
        "/news-aggregator/dev/supabase_db_url",
        "/news-aggregator/dev/openai_api_key",
        "/news-aggregator/dev/resend_api_key",
    }
    for call in fake_ssm.put_parameter.call_args_list:
        assert call.kwargs["Type"] == "SecureString"
        assert call.kwargs["Overwrite"] is True
```

- [ ] **Step 2: Run — expect fail**

```bash
uv run pytest services/scraper/src/news_scraper/tests/unit/test_sync_secrets.py -v
```

Expected: FAIL — `FileNotFoundError` or similar (script doesn't exist yet).

- [ ] **Step 3: Create `infra/scraper/sync_secrets.py`**

```python
"""Push .env sensitive values into SSM Parameter Store (SecureString).

Run after `terraform apply` creates the placeholder params:

    uv run python infra/scraper/sync_secrets.py --env dev
"""

from __future__ import annotations

import argparse
import os
import sys

import boto3
from dotenv import find_dotenv, load_dotenv

ENV_TO_PARAM: dict[str, str] = {
    "SUPABASE_DB_URL": "supabase_db_url",
    "SUPABASE_POOLER_URL": "supabase_pooler_url",
    "OPENAI_API_KEY": "openai_api_key",
    "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
    "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
    "YOUTUBE_PROXY_USERNAME": "youtube_proxy_username",
    "YOUTUBE_PROXY_PASSWORD": "youtube_proxy_password",
    "RESEND_API_KEY": "resend_api_key",
}


def push_params(ssm_client: object, env: str) -> int:
    """Push all set .env values to SSM. Returns number of params pushed."""
    pushed = 0
    for env_key, param_suffix in ENV_TO_PARAM.items():
        value = os.environ.get(env_key)
        if not value:
            print(f"skip {env_key} (not set)")
            continue
        name = f"/news-aggregator/{env}/{param_suffix}"
        ssm_client.put_parameter(  # type: ignore[attr-defined]
            Name=name, Value=value, Type="SecureString", Overwrite=True
        )
        print(f"pushed {name}")
        pushed += 1
    return pushed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", required=True, choices=["dev", "prod"])
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "aiengineer"))
    args = parser.parse_args()

    load_dotenv(find_dotenv())
    session = boto3.Session(profile_name=args.profile)
    ssm = session.client("ssm")
    count = push_params(ssm, env=args.env)
    print(f"done: {count} parameters updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect pass**

```bash
uv run pytest services/scraper/src/news_scraper/tests/unit/test_sync_secrets.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Smoke-test against AWS**

```bash
uv run python infra/scraper/sync_secrets.py --env dev
```

Expected: prints one `pushed /news-aggregator/dev/<name>` per `.env` value that's set, and `done: N parameters updated`.

- [ ] **Step 6: Commit**

```bash
git add infra/scraper/sync_secrets.py \
        services/scraper/src/news_scraper/tests/unit/test_sync_secrets.py
git commit -m "feat(infra): sync_secrets.py for pushing .env to SSM SecureString"
```

---

### Task 6.2: Update `deploy.py` — real `cmd_deploy`

**Files:**
- Modify: `services/scraper/deploy.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_deploy.py`

- [ ] **Step 1: Write failing test**

Create `services/scraper/src/news_scraper/tests/unit/test_deploy.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPT = Path(__file__).resolve().parents[5] / "services" / "scraper" / "deploy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("deploy", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deploy"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tf_dir_points_at_scraper_module() -> None:
    mod = _load_module()
    # We're asserting the change we're about to make: tf_dir = infra/scraper, not infra/envs/*
    assert mod._terraform_dir().name == "scraper"
    assert mod._terraform_dir().parent.name == "infra"


def test_cmd_deploy_calls_terraform_workspace_and_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(mod, "cmd_build", lambda: 0)
    monkeypatch.setattr(mod, "_smoke_healthz", lambda url: None)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    rc = mod.cmd_deploy(env="dev")

    assert rc == 0
    # Expect at least a workspace-select and an apply
    assert any(c[0:3] == ["terraform", "workspace", "select"] for c in calls)
    apply_calls = [c for c in calls if c[0:2] == ["terraform", "apply"]]
    assert len(apply_calls) == 1
    apply_cmd = apply_calls[0]
    assert "-auto-approve" in apply_cmd
    assert any(a.startswith("-var=image_tag=") for a in apply_cmd)
    assert "-replace=aws_ecs_express_gateway_service.scraper" in apply_cmd
```

- [ ] **Step 2: Run — expect fail**

```bash
uv run pytest services/scraper/src/news_scraper/tests/unit/test_deploy.py -v
```

Expected: 2 failures — `_terraform_dir` doesn't exist; `_smoke_healthz` doesn't exist; `cmd_deploy` still has the old tf_dir path.

- [ ] **Step 3: Update `services/scraper/deploy.py`**

Replace the module contents with:

```python
"""Scraper deploy orchestrator.

Two modes:
  build   — docker build + push to ECR (works standalone)
  deploy  — build + push + terraform apply to update the ECS Express service

Examples:
  uv run python services/scraper/deploy.py --mode build
  uv run python services/scraper/deploy.py --mode deploy --env dev
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import boto3


def _profile() -> str:
    return os.environ.get("AWS_PROFILE", "aiengineer")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=_profile())


def _account_id(session: boto3.Session) -> str:
    return session.client("sts").get_caller_identity()["Account"]  # type: ignore[no-any-return]


def _region(session: boto3.Session) -> str:
    region = (
        session.region_name
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
    )
    if not region:
        raise RuntimeError(
            "AWS region not set (profile default, AWS_REGION, or AWS_DEFAULT_REGION)"
        )
    return region


def _ecr_repo() -> str:
    return os.environ.get("ECR_REPO_NAME", "news-scraper")


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _terraform_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "infra" / "scraper"


def _full_image_uri(session: boto3.Session, tag: str) -> str:
    return (
        f"{_account_id(session)}.dkr.ecr.{_region(session)}.amazonaws.com/"
        f"{_ecr_repo()}:{tag}"
    )


def _ecr_login(session: boto3.Session) -> None:
    region = _region(session)
    account = _account_id(session)
    cmd = (
        f"aws ecr get-login-password --region {region} --profile {_profile()} | "
        f"docker login --username AWS --password-stdin "
        f"{account}.dkr.ecr.{region}.amazonaws.com"
    )
    subprocess.run(cmd, shell=True, check=True)  # noqa: S602


def _build_image(sha_tag: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(Path(__file__).parent / "Dockerfile"),
            "-t",
            sha_tag,
            "--build-arg",
            f"GIT_SHA={_git_sha()}",
            str(repo_root),
        ],
        check=True,
    )


def _push_image(session: boto3.Session, sha_tag: str) -> None:
    uri_sha = _full_image_uri(session, _git_sha())
    uri_latest = _full_image_uri(session, "latest")
    subprocess.run(["docker", "tag", sha_tag, uri_sha], check=True)
    subprocess.run(["docker", "tag", sha_tag, uri_latest], check=True)
    subprocess.run(["docker", "push", uri_sha], check=True)
    subprocess.run(["docker", "push", uri_latest], check=True)
    print(f"pushed {uri_sha}")
    print(f"pushed {uri_latest}")


def _smoke_healthz(url: str) -> None:
    """Curl /healthz; assert 200 and that git_sha matches HEAD."""
    expected = _git_sha()
    # Retry for up to 3 minutes — ECS may still be rolling tasks.
    deadline = time.time() + 180
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=10) as resp:  # noqa: S310
                body = resp.read().decode()
                if f'"git_sha":"{expected}"' in body:
                    print(f"healthz OK: {body}")
                    return
                print(f"healthz returned old sha: {body}; retrying...")
        except Exception as exc:
            last_err = exc
            print(f"healthz attempt failed: {exc}; retrying...")
        time.sleep(10)
    raise RuntimeError(
        f"healthz did not reach expected git_sha={expected} within 3 min: {last_err}"
    )


def cmd_build() -> int:
    session = _session()
    _ecr_login(session)
    local_tag = f"news-scraper:{_git_sha()}"
    _build_image(local_tag)
    _push_image(session, local_tag)
    return 0


def cmd_deploy(env: str) -> int:
    """Build + push + terraform apply + smoke test."""
    if cmd_build() != 0:
        return 1

    tf_dir = _terraform_dir()
    if not tf_dir.exists():
        print(
            f"ERROR: {tf_dir} does not exist. Run the bootstrap + scraper init first.",
            file=sys.stderr,
        )
        return 3

    sha = _git_sha()
    tf_env = {**os.environ, "AWS_PROFILE": _profile()}

    # Select workspace (create if missing)
    try:
        subprocess.run(
            ["terraform", "workspace", "select", env],
            cwd=tf_dir,
            check=True,
            env=tf_env,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["terraform", "workspace", "new", env],
            cwd=tf_dir,
            check=True,
            env=tf_env,
        )

    subprocess.run(
        [
            "terraform",
            "apply",
            "-auto-approve",
            f"-var=image_tag={sha}",
            "-replace=aws_ecs_express_gateway_service.scraper",
        ],
        cwd=tf_dir,
        check=True,
        env=tf_env,
    )

    _smoke_healthz(f"https://scraper.patrickcmd.dev/healthz")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["build", "deploy"], required=True)
    parser.add_argument("--env", default="dev")
    args = parser.parse_args()
    if args.mode == "build":
        return cmd_build()
    return cmd_deploy(args.env)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run — expect pass**

```bash
uv run pytest services/scraper/src/news_scraper/tests/unit/test_deploy.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Run full check**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy packages services/scraper/src
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add services/scraper/deploy.py \
        services/scraper/src/news_scraper/tests/unit/test_deploy.py
git commit -m "feat(scraper): real deploy.py cmd_deploy — terraform workspace + apply + smoke test"
```

---

### Task 6.3: Makefile targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add new targets + update `.PHONY`**

Open `Makefile`. Replace the `.PHONY` line to include the new targets:

```makefile
.PHONY: help install install-dev pre-commit-install \
        fmt lint typecheck check \
        test test-unit test-integration \
        test-scraper-unit test-scraper-live \
        scraper-build scraper-deploy-build scraper-deploy \
        scraper-serve scraper-ingest \
        tf-bootstrap tf-scraper-init tf-scraper-plan tf-scraper-apply \
        secrets-sync \
        migrate migrate-down migrate-rev migration-history migration-current \
        seed reset-db \
        clean tag-foundation tag-ingestion
```

Then insert an `infra` section before `# ---------- database ----------`:

```makefile
# ---------- infra ----------

tf-bootstrap: ## One-time Terraform state-backend bootstrap
	cd infra/bootstrap && terraform init && terraform apply

tf-scraper-init: ## Initialize scraper Terraform (first time or after backend change)
	@test -n "$(STATE_BUCKET)" || (echo "STATE_BUCKET required" && exit 1)
	cd infra/scraper && terraform init \
	  -backend-config="bucket=$(STATE_BUCKET)" \
	  -backend-config="key=scraper/terraform.tfstate" \
	  -backend-config="region=us-east-1" \
	  -backend-config="dynamodb_table=news-aggregator-tf-locks"

tf-scraper-plan: ## Show scraper Terraform plan
	cd infra/scraper && terraform plan

tf-scraper-apply: ## Apply scraper Terraform
	cd infra/scraper && terraform apply

secrets-sync: ## Push .env secrets into SSM (requires ENV=dev|prod)
	@test -n "$(ENV)" || (echo "ENV required: make secrets-sync ENV=dev" && exit 1)
	uv run python infra/scraper/sync_secrets.py --env $(ENV)
```

- [ ] **Step 2: Verify**

```bash
make help | grep -E 'tf-|secrets-sync'
```

Expected output (order-agnostic):

```
tf-bootstrap            One-time Terraform state-backend bootstrap
tf-scraper-init         Initialize scraper Terraform ...
tf-scraper-plan         Show scraper Terraform plan
tf-scraper-apply        Apply scraper Terraform
secrets-sync            Push .env secrets into SSM ...
```

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "build(make): add Terraform + secrets-sync targets"
```

---

### Task 6.4: `infra/README.md`

**Files:**
- Create: `infra/README.md`

- [ ] **Step 1: Write `infra/README.md`**

```markdown
# Infrastructure (Terraform)

Per-sub-project Terraform root modules. Each deployable owns its own `infra/<name>/` dir,
independently applied, sharing a common remote-state backend.

## Conventions

- **One root module per deployable.** `infra/scraper/`, later `infra/agents/`, `infra/api/`, `infra/frontend/`, `infra/scheduler/`.
- **Remote state:** S3 (`news-aggregator-tf-state-<account-id>`) + DynamoDB locking (`news-aggregator-tf-locks`), created once by `infra/bootstrap/`.
- **Per-env separation:** Terraform workspaces (`dev`, `prod`), not duplicated directories.
- **AWS auth:** `AWS_PROFILE=aiengineer` (default). Override with `export AWS_PROFILE=<other>`.
- **Secrets:** live in SSM Parameter Store (SecureString). Pushed via `sync_secrets.py`, not Terraform.

## One-time bootstrap

Creates the state bucket + lock table. Run once, ever.

```sh
make tf-bootstrap
# Records state_bucket_name, lock_table_name, account_id in Terraform output.
```

Bootstrap uses **local state** (gitignored) — it can't depend on the backend it's creating. If the local state file is lost, recover with:

```sh
cd infra/bootstrap
terraform import aws_s3_bucket.tf_state news-aggregator-tf-state-<account-id>
terraform import aws_dynamodb_table.tf_lock news-aggregator-tf-locks
```

## Scraper module

```sh
# First time only: initialize the backend (STATE_BUCKET from bootstrap output)
make tf-scraper-init STATE_BUCKET=news-aggregator-tf-state-<account>

cd infra/scraper
terraform workspace new dev   # or `terraform workspace select dev`
terraform apply

make secrets-sync ENV=dev     # push .env values into SSM
```

Subsequent deploys just run `make scraper-deploy`, which builds the image and runs `terraform apply -replace=aws_ecs_express_gateway_service.scraper`.

## Adding a new sub-project module

1. `mkdir infra/<name>`
2. Copy `infra/scraper/backend.tf` and adjust the backend `key` to `<name>/terraform.tfstate`.
3. Write module-specific Terraform.
4. `terraform init -backend-config=...` (same bucket, different key).
5. Follow the same workspace pattern (`dev`/`prod`).
```

- [ ] **Step 2: Commit**

```bash
git add infra/README.md
git commit -m "docs(infra): README for Terraform conventions + per-module setup"
```

---

### Task 6.5: Trim `docs/ecs-express-bootstrap.md`

**Files:**
- Modify: `docs/ecs-express-bootstrap.md`

- [ ] **Step 1: Replace the file contents**

Replace the entire file with:

```markdown
# ECS Express — prerequisites

Terraform (in `infra/scraper/`) provisions the ECS Express service, IAM roles,
ECR repo, SSM params, ACM cert, and Route53 records. Before applying it, make
sure these exist manually in your AWS account:

1. **Route53 hosted zone for `patrickcmd.dev`** — required for the ACM DNS
   validation and the scraper's A-alias record.

Nothing else needs manual setup. See [infra/README.md](../infra/README.md) for
the full bootstrap walkthrough.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ecs-express-bootstrap.md
git commit -m "docs: trim ECS Express bootstrap to prerequisites only (Terraform owns the rest)"
```

---

### Task 6.6: Root README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the `### Build and deploy` subsection under "Running the scraper"**

Find the existing block:

```
### Build and deploy

```sh
make scraper-build               # local docker build
make scraper-deploy-build        # build + push to ECR (requires AWS_PROFILE=aiengineer)
make scraper-deploy              # full deploy via Terraform (requires #6 infra)
```

See [docs/ecs-express-bootstrap.md](docs/ecs-express-bootstrap.md) for one-time AWS setup until sub-project #6 codifies it in Terraform.
```

Replace with:

```
### Build and deploy

```sh
make tf-bootstrap                    # one-time: Terraform state backend
make tf-scraper-init STATE_BUCKET=news-aggregator-tf-state-<account>  # first time only
make tf-scraper-apply                # provision AWS infra
make secrets-sync ENV=dev            # push .env secrets into SSM

make scraper-build                   # local docker build only
make scraper-deploy-build            # build + push to ECR
make scraper-deploy                  # end-to-end: build + push + terraform apply + smoke test
```

The scraper ships at `https://scraper.patrickcmd.dev/`.

See [infra/README.md](infra/README.md) for Terraform conventions.
See [docs/ecs-express-bootstrap.md](docs/ecs-express-bootstrap.md) for the (minimal) manual prerequisites.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): point scraper deploy flow at Terraform"
```

---

### Task 6.7: Final end-to-end smoke + tag

**Files:** (no code changes)

- [ ] **Step 1: Run the full suite**

```bash
make check
```

Expected: all green (ruff, mypy, 114+ tests — new `test_sync_secrets.py` and `test_deploy.py` add ~4 tests).

- [ ] **Step 2: End-to-end smoke via `make scraper-deploy`**

```bash
make scraper-deploy
```

Expected:

- `docker build` completes (~1–2 min on warm cache).
- `docker push` completes.
- `terraform apply -replace=...` replaces the service with the new image tag.
- `_smoke_healthz` returns with `healthz OK: {"status":"ok","git_sha":"<new sha>"}` after the ALB drains the old task.

- [ ] **Step 3: Tag**

```bash
git tag -a ingestion-v0.2.1 -m "Sub-project #1 Ingestion — Terraform IaC"
git log --oneline -1
```

Expected: new tag created.

- [ ] **Step 4: Pause for user approval before pushing**

Do NOT push automatically. Ask the user whether to push branch + tag:

```
git push -u origin sub-project#1
git push origin ingestion-v0.2.1
```

---

## Appendix A — Command cheat sheet

```sh
# Plan against the current workspace without applying
make tf-scraper-plan

# See current state
cd infra/scraper && terraform state list

# Import an orphaned resource (e.g., if bootstrap state is lost)
terraform import <resource> <id>

# Destroy the scraper service (keep cluster + ECR)
cd infra/scraper && terraform destroy -target=aws_ecs_express_gateway_service.scraper

# Switch env
terraform workspace select prod

# Tail scraper logs
aws logs tail /ecs/news-scraper --follow --profile aiengineer
```

## Appendix B — Known risks in this implementation

Per the spec §12:

- **`aws_ecs_express_gateway_service` is new.** Attribute names (`alb_dns_name`, `alb_zone_id`) are assumed per Context7 docs at spec time. Task 5.3's fallback (data-source lookup by tag) handles the case if they're not yet exposed.
- **Infrastructure role managed policy TBD.** Task 3.4 documents the verification step; inline policy is the fallback.
- **Scale-to-zero risk.** `min_capacity=0` + CPU-tracking + `scale_in_cooldown=1800s` is the current mitigation. Revisit in #3 if background runs consistently exceed 30 min.
- **Bootstrap state is local + gitignored.** Task 6.4 (infra README) documents `terraform import` recovery.

## Self-review (author)

- Spec §2 scope — all "In scope" items covered across Phases 1–6. "Out of scope" items (Lambda/API Gateway/CloudFront/CI/WAF/NAT) intentionally absent.
- Spec §3 architectural decisions — every row mapped to a task: bootstrap (Task 1.1–1.2); scraper scaffold (Task 2.1); ECR/cluster/logs/IAM/SSM (Task 3.1–3.5); ACM/Route53 (Task 4.1, 5.3); service (Task 5.2); autoscaling (Task 5.4); deploy.py (Task 6.2); sync_secrets (Task 6.1); per-sub-project convention (Task 6.4).
- Spec §4 directory layout — matches Tasks 1.1 and 2.1–2.5 outputs.
- Spec §5/§6 resource lists — every resource defined in spec has a task that creates it.
- Spec §7 sync_secrets — Task 6.1 implements; `ENV_TO_PARAM` matches spec map exactly.
- Spec §8 deploy.py — Task 6.2 implements; attributes (`_terraform_dir`, `_smoke_healthz`, `cmd_deploy` workspace select + apply + replace) covered by both the prose and the unit tests.
- Spec §9 apply order + Makefile — Task 6.3 implements the Makefile; Tasks 1.2, 3.6, 4.1, 5.5 walk the apply order.
- Spec §10 docs — Tasks 6.4, 6.5, 6.6.
- Spec §12 risks — mitigations in Appendix B; Task 3.4 verification step; Task 5.3 fallback.
- Placeholder scan — no "TBD/TODO/later" left in executable steps. The infrastructure-role verification step is a *concrete instruction* (run `aws iam list-policies`, replace if a managed policy exists), not a placeholder.
- Type consistency — `ENV_TO_PARAM` keys/values used identically across `sync_secrets.py` and the test. `_terraform_dir()`, `_smoke_healthz()`, `cmd_deploy()` names consistent in `deploy.py` and tests. SSM param names consistent between `ssm.tf`, `iam.tf` policy, service secret refs, and sync_secrets.py.
