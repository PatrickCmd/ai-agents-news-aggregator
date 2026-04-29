# Sub-project #6 — CI/CD + Ops

**Status:** approved (2026-04-28)
**Tag:** `cicd-ops-v0.8.0`
**Goal:** bring sub-projects #1–#4 to the same CI/CD bar that #5 set, add per-Lambda observability, ship the first three operational runbooks, and extend dependabot to Terraform.
**Out of scope:** cost dashboards, Slack/Chatbot integration, secret rotation, paid-tier email, Python uv dependabot, ECS-level scraper alarms, auto-deploy on tag/main, centralised log aggregation.

---

## 1. Problem

Sub-project #5 shipped a complete CI/CD + observability story for the frontend: workflow_dispatch deploys via OIDC, dependabot, OSV-Scanner, dependabot-bumped supply chain. The backend services that have been live since #1 — scraper (ECS Express), three agent Lambdas, scheduler Lambda + Step Functions, the API Lambda — are still deployed via local `make X-deploy` only. There is no CI path; if the operator's laptop is unavailable, nothing ships.

Per-Lambda alarms are also missing. Today's signals are limited to:

- `cron_failed` (Step Functions execution failed)
- `cron_stale-36h` (no successful cron in 36h)
- `api_5xx` (≥5 API Gateway 5XXs in 5min)

Three real alarms across the entire backend, none of which page anyone — they have no `alarm_actions`. They are dashboard-only.

There are no runbooks documenting "what to do when this fires."

## 2. Scope (locked)

This sub-project ships:

1. **Two workflow_dispatch deploy workflows** — `scraper-deploy.yml`, `lambda-deploy.yml` — for the six existing backend services.
2. **One shared deploy script** — `scripts/lambda-deploy.sh` — wrapping the existing per-service `services/<x>/deploy.py` scripts so local and CI use the same code path. Plus `scripts/scraper-deploy.sh` for the ECS-shaped service.
3. **One new Terraform module** — `infra/alerts/` — owning the per-env SNS topic + email subscription (prod only) + SSM parameter publishing the topic ARN.
4. **Per-(service, env) OIDC IAM roles** — 18 roles total (6 services × 3 envs), one `github_oidc.tf` per existing service module.
5. **Per-Lambda alarms** — 10 new (`Errors` + `Throttles` for 5 Lambda services), wired to publish to the new SNS topic.
6. **`alarm_actions` migration** for the 3 existing alarms — they now publish to the new SNS topic.
7. **Per-service CloudWatch log retention** — 30d (dev/test) / 90d (prod), 15 log groups total.
8. **Three runbooks** — `cron-pipeline-failure.md`, `api-5xx-spike.md`, `scraper-degraded.md`.
9. **Dependabot expansion** — 9 new `terraform` ecosystem entries, one per Terraform root.

## 3. Architecture overview

```
.github/workflows/
├── scraper-deploy.yml        NEW — ECS deploy via OIDC, workflow_dispatch
└── lambda-deploy.yml         NEW — Lambda deploy via OIDC, choice of [digest|editor|email|scheduler|api]

scripts/
├── lambda-deploy.sh          NEW — shared by all 5 Lambda services + lambda-deploy.yml
└── scraper-deploy.sh         NEW — wraps services/scraper/deploy.py for the ECS path

infra/
├── alerts/                   NEW — per-env SNS topic + prod email + SSM ARN export
│   ├── backend.tf
│   ├── data.tf
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── digest/github_oidc.tf     NEW — per-(service, env) IAM role
├── digest/alarms.tf          NEW — Errors + Throttles alarms publishing to SSM-resolved SNS topic
├── editor/github_oidc.tf     NEW — same shape
├── editor/alarms.tf          NEW
├── email/github_oidc.tf      NEW
├── email/alarms.tf           NEW
├── scheduler/github_oidc.tf  NEW
├── scheduler/alarms.tf       NEW (Lambda alarms; existing cron alarms stay in eventbridge.tf with alarm_actions added)
├── api/github_oidc.tf        NEW
├── api/alarms.tf             NEW (Lambda alarms; existing api_5xx stays in apigateway.tf with alarm_actions added)
└── scraper/github_oidc.tf    NEW — ECS-shaped (ECR push + ECS service update perms)

docs/runbooks/                NEW
├── cron-pipeline-failure.md
├── api-5xx-spike.md
└── scraper-degraded.md

.github/dependabot.yml        MODIFY — add 9 terraform ecosystem entries
```

No new compute resources. No new state files except `infra/alerts/`. No changes to how scraper/agents/scheduler/api are deployed locally — `make X-deploy` continues to work as before because both local and CI call the same `services/<x>/deploy.py`.

## 4. Workflow design

### 4.1 Trigger model

`workflow_dispatch` only for both workflows. No auto-deploy on tag, push, or merge. Mirrors sub-project #5's pattern. Operator picks env + (for `lambda-deploy.yml`) service + clicks Run.

### 4.2 `scraper-deploy.yml`

```yaml
name: scraper-deploy
on:
  workflow_dispatch:
    inputs:
      environment: { type: choice, options: [dev, test, prod], default: dev }
      action:      { type: choice, options: [deploy, destroy], default: deploy }

permissions: { id-token: write, contents: read }
concurrency: scraper-${{ inputs.environment }}

jobs:
  run:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars.AWS_DEPLOY_ROLE_ARN }}
          aws-region: us-east-1
      - uses: astral-sh/setup-uv@v3
      - if: ${{ inputs.action == 'deploy' }}
        run: ./scripts/scraper-deploy.sh ${{ inputs.environment }}
      - if: ${{ inputs.action == 'destroy' }}
        working-directory: infra/scraper
        run: |
          terraform init -backend-config="bucket=news-aggregator-tf-state-${{ vars.AWS_ACCOUNT_ID }}" -backend-config="key=scraper/terraform.tfstate" -backend-config="region=us-east-1"
          terraform workspace select ${{ inputs.environment }}
          terraform destroy -auto-approve
```

### 4.3 `lambda-deploy.yml`

```yaml
name: lambda-deploy
on:
  workflow_dispatch:
    inputs:
      service:     { type: choice, options: [digest, editor, email, scheduler, api] }
      environment: { type: choice, options: [dev, test, prod], default: dev }

permissions: { id-token: write, contents: read }
concurrency: lambda-${{ inputs.service }}-${{ inputs.environment }}

jobs:
  run:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ vars[format('AWS_DEPLOY_ROLE_ARN_{0}', inputs.service)] }}
          aws-region: us-east-1
      - uses: astral-sh/setup-uv@v3
      - run: ./scripts/lambda-deploy.sh ${{ inputs.service }} ${{ inputs.environment }}
```

The `format()` lookup dispatches to `AWS_DEPLOY_ROLE_ARN_DIGEST`, `_EDITOR`, `_EMAIL`, `_SCHEDULER`, `_API` — env-level GitHub vars set after Terraform apply (output the role ARN, paste into GitHub Environment vars, same flow as #5 web).

### 4.4 `scripts/lambda-deploy.sh`

```bash
#!/usr/bin/env bash
# scripts/lambda-deploy.sh <service> <env>
set -euo pipefail

SVC="${1:?usage: $0 <service> <env>}"
ENV="${2:?usage: $0 <service> <env>}"

case "$SVC" in
  digest|editor|email)
    uv run python "services/agents/$SVC/deploy.py" --mode deploy --env "$ENV"
    ;;
  scheduler|api)
    uv run python "services/$SVC/deploy.py" --mode deploy --env "$ENV"
    ;;
  *)
    echo "unknown service: $SVC (must be digest|editor|email|scheduler|api)" >&2
    exit 2
    ;;
esac
```

`scripts/scraper-deploy.sh` is a one-liner that calls `services/scraper/deploy.py --mode deploy --env "$1"`. Kept separate because the ECS path doesn't share the Lambda zip flow.

## 5. OIDC IAM roles

### 5.1 Scope — per (service, env)

18 roles total. Each `infra/<service>/github_oidc.tf` defines a role gated by:

```hcl
StringLike = {
  "token.actions.githubusercontent.com:sub" = "repo:PatrickCmd/ai-agents-news-aggregator:environment:${terraform.workspace}"
}
```

Role naming: `gh-actions-deploy-{service}-{env}`. Example: `gh-actions-deploy-digest-dev`.

### 5.2 Per-role policy scope

**Lambda services (digest, editor, email, scheduler, api):**

- `lambda:UpdateFunctionCode` on `arn:aws:lambda:*:*:function:news-{service}-{env}`
- `s3:PutObject`, `s3:GetObject` on `arn:aws:s3:::news-aggregator-lambda-artifacts-{ACCT}/*` (the lambda artifact bucket from `infra/bootstrap/`)
- `s3:GetObject`, `s3:PutObject` on `arn:aws:s3:::news-aggregator-tf-state-{ACCT}/<service>/*` (terraform state)
- `s3:ListBucket` on the state bucket (terraform state list)
- The full set of resource permissions terraform needs to apply that service's module — `lambda:GetFunction`, `lambda:UpdateFunctionConfiguration`, `iam:PassRole` on the Lambda execution role, `cloudwatch:*` on the alarms in scope, etc. Each `github_oidc.tf` will scope these to ARNs in the same module only.

**Scraper:**

- `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`, `ecr:CompleteLayerUpload`, `ecr:BatchCheckLayerAvailability`, `ecr:GetAuthorizationToken` on the scraper ECR repo
- `ecs:UpdateService`, `ecs:DescribeServices`, `ecs:RegisterTaskDefinition` on the scraper service / task definition
- Terraform state perms identical to Lambda services

The exact policy documents land in implementation; the design commits to: each role has only the perms its `services/<x>/deploy.py` needs, plus terraform-state for the same module.

## 6. Observability

### 6.1 `infra/alerts/` module

```hcl
# infra/alerts/main.tf
resource "aws_sns_topic" "alerts" {
  name = "news-alerts-${terraform.workspace}"
}

resource "aws_sns_topic_subscription" "email_prod" {
  count     = terraform.workspace == "prod" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_ssm_parameter" "alerts_topic_arn" {
  name  = "/news-aggregator/${terraform.workspace}/sns-alerts-arn"
  type  = "String"
  value = aws_sns_topic.alerts.arn
}
```

`var.alert_email` is set per env via `terraform.tfvars` (gitignored). For `dev`/`test`, the variable is unused (no subscription — `count = 0`).

### 6.2 Per-Lambda alarms

Each `infra/<lambda-service>/alarms.tf` reads the SSM ARN and defines two alarms:

```hcl
data "aws_ssm_parameter" "alerts_arn" {
  name = "/news-aggregator/${terraform.workspace}/sns-alerts-arn"
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "news-${local.service}-${terraform.workspace}-errors"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  alarm_actions       = [data.aws_ssm_parameter.alerts_arn.value]
  alarm_description   = "Lambda news-${local.service}-${terraform.workspace} returned ≥1 unhandled error in 5min."
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name          = "news-${local.service}-${terraform.workspace}-throttles"
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  period              = 300
  statistic           = "Sum"
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  alarm_actions       = [data.aws_ssm_parameter.alerts_arn.value]
  alarm_description   = "Lambda news-${local.service}-${terraform.workspace} hit concurrency throttle ≥1× in 5min."
}
```

`local.service` is `"digest"`, `"editor"`, etc. — defined in each module's `locals` block.

### 6.3 Existing alarm migration

Three existing alarms gain an `alarm_actions = [data.aws_ssm_parameter.alerts_arn.value]` line:

- `infra/scheduler/eventbridge.tf` — `cron_failed`, `cron_stale`
- `infra/api/apigateway.tf` — `api_5xx`

Each module also gains the `data "aws_ssm_parameter" "alerts_arn"` block.

### 6.4 Scraper

No new ECS-level alarms. Scraper failures surface as `http:invoke` failures in the cron Step Functions execution, which is already covered by `cron_failed`.

### 6.5 Log retention

Per Lambda service (5 services), per workspace, an `aws_cloudwatch_log_group` resource with explicit `retention_in_days`:

```hcl
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/news-${local.service}-${terraform.workspace}"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}
```

If a log group already exists from a prior implicit creation, terraform import is required (documented in the implementation plan).

## 7. Runbooks

Three runbooks under `docs/runbooks/`. Each follows a 5-section template:

```markdown
# <Alarm name>

**Symptom:** <what fired and what the user sees>

**Triage (first 2 min):**
- <command 1>
- <command 2>

**Diagnose:**
- Common cause A — how to confirm, where to look
- Common cause B — …

**Remediate:**
- Fix path 1 (most common)
- Fix path 2 (less common)
- Rollback recipe

**Postmortem:** capture in `docs/postmortems/YYYY-MM-DD-<incident>.md`
```

### 7.1 `cron-pipeline-failure.md`

Symptom: `news-cron-pipeline-failed-prod` or `news-cron-pipeline-stale-prod` alarm. No daily digest sent.

Triage commands: `make cron-history`, `gh run list`, `aws stepfunctions get-execution-history --execution-arn <arn>`.

Common causes: scraper http-invoke timeout (60-iteration poll cap hit), per-article digest Lambda errors swallowed by `ToleratedFailurePercentage=100`, OpenAI quota exceeded, rss-mcp / Playwright MCP subprocess crash, Resend rate-limit (when ≥3 daily users on free tier).

Remediation: `make cron-invoke` to re-run, `make scraper-pin-up` if scraper looks cold, inspect Langfuse traces for digest/editor/email per-call failures, check OpenAI dashboard for rate limit.

### 7.2 `api-5xx-spike.md`

Symptom: `news-api-prod-5xx` alarm — ≥5 5XX in 5min.

Triage: `make api-logs SINCE=10m`, API Gateway dashboard, `make api-invoke` for healthz.

Common causes: Clerk JWKS fetch timeout (cold key cache), DB pool exhausted (asyncpg-on-loop bug regression), Lambda cold-start cascade after a deploy, Mangum ASGI-translation bug, missing env var.

Remediation: rollback to previous git tag (`make api-deploy` from prior commit), verify Clerk issuer URL hasn't changed, restart Lambda (force update), check `news_db.engine.reset_engine()` is being called in the handler.

### 7.3 `scraper-degraded.md`

Symptom: cron pipeline alarm where Step Functions history shows scraper as the failing stage.

Triage: `make scraper-status`, `make scraper-logs`, ECS service events in console.

Common causes: Playwright MCP crash, rss-mcp disk pressure, Fargate task recycled mid-run, ECR image corruption, scraper container OOM.

Remediation: `make scraper-redeploy` (force pull `:latest`), `make scraper-pin-up` to keep warm during repro, scale task memory in `infra/scraper/` if recurring OOM, check ECR image tags.

## 8. Dependabot

`.github/dependabot.yml` gains 9 new `terraform` entries:

```yaml
  - package-ecosystem: terraform
    directory: "/infra/bootstrap"
    schedule: { interval: weekly }
    labels: ["dependencies", "infra"]
  # ...repeat for: alerts, scraper, digest, editor, email, scheduler, api, web
```

The existing `npm /web` and `github-actions /` entries stay unchanged. Python `uv` is out of scope (ecosystem still beta).

## 9. Testing strategy

### 9.1 Pre-apply (subagent verification)

Each Terraform-touching task runs `terraform fmt -check && terraform validate -backend=false` against the affected module. Same as #5 Phase 8.

Workflow YAML: `python3 -c 'import yaml; yaml.safe_load(open(...))'` per file.

Bash scripts: `bash -n scripts/lambda-deploy.sh && bash -n scripts/scraper-deploy.sh`.

### 9.2 Post-apply smoke (operator-driven, dev workspace)

Once Terraform is applied to `dev` for the alerts module + at least one service module:

1. **SNS plumbing.** `aws sns publish --topic-arn $(...) --message "test"`. In `dev` no email arrives (no subscription) — confirm via SNS console.
2. **Per-service deploy via workflow.** `gh workflow run lambda-deploy.yml -f service=digest -f environment=dev` — confirm AssumeRole succeeds and terraform apply is idempotent (no resource changes if nothing else moved).
3. **Alarm wiring.** Force a Lambda error: `aws lambda invoke --function-name news-digest-dev --payload '{"intentionally":"broken"}' /tmp/out.json`. Wait 5–7 min. Confirm `news-digest-dev-errors` transitions to `ALARM` in CloudWatch.
4. **Runbook walk.** For each of the 3 runbooks, run every command in the "Triage" section against `dev`. All commands must produce non-error output.

### 9.3 Production verification

Apply to `prod` only after `dev` and `test` are green. After `terraform apply` for `infra/alerts/` in `prod`, AWS sends a one-time confirmation email to `var.alert_email` — **the operator must click "Confirm subscription"** in that email before any subsequent SNS messages will deliver. Then publish a manual test message via `aws sns publish` with the prod topic ARN and confirm it lands.

## 10. Acceptance

Sub-project #6 ships when:

- [ ] `infra/alerts/` module applies cleanly to dev, test, and prod workspaces.
- [ ] All 6 modified backend modules apply cleanly to all 3 workspaces (no drift, no destroy).
- [ ] 18 OIDC roles exist (verifiable via `aws iam list-roles | grep gh-actions-deploy`).
- [ ] 10 new alarms exist in each workspace (verifiable via `aws cloudwatch describe-alarms`); 3 existing alarms have `alarm_actions` populated.
- [ ] 15 log groups have explicit retention (30d or 90d depending on workspace).
- [ ] Both `scraper-deploy.yml` and `lambda-deploy.yml` successfully run via `gh workflow run` for at least one service in `dev`.
- [ ] At least one test SNS message reaches the subscribed inbox in prod.
- [ ] All 3 runbooks committed; their triage commands produce sensible output against dev.
- [ ] `dependabot.yml` has 9 terraform entries.
- [ ] Tag `cicd-ops-v0.8.0` created.
- [ ] `README.md` and `AGENTS.md` reflect #6 as shipped.

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Adding `alarm_actions` to existing alarms changes Terraform state for `infra/scheduler/` and `infra/api/`. A bad apply could destabilise live alarms. | Plan + apply in `dev` first, confirm no other drift, then apply to `test`/`prod`. |
| 18 IAM roles increases the IAM API surface and the chance of policy bugs. | Each role's policy scope is narrow (single service, single env). Roles are gated by `sub` claim restricting to repo + env. |
| `aws_cloudwatch_log_group` for each Lambda may collide with implicitly-created log groups from prior deploys. | Implementation plan includes a `terraform import` step per log group if `aws logs describe-log-groups` shows it already exists. |
| Provider version drift across modules (e.g., bootstrap on aws@6.42.0, web/api on ~> 5.60) — dependabot weekly bumps could cause divergent state across modules. | Accept this — drift is already there pre-#6; dependabot makes it visible rather than hidden. Operator merges PRs intentionally. |
| `ToleratedFailurePercentage=100` swallows agent Lambda errors in the cron pipeline. New per-Lambda `Errors` alarm now surfaces these — could be noisy in dev. | By design — alarms exist in dev but no SNS subscription, so they're dashboard-only. Switch to email later if needed. |
| Scraper destroy path requires terraform destroy via OIDC — the scraper deploy role probably can't destroy itself (chicken-and-egg). | Documented as "destroy is a developer convenience only" with a workflow comment, same pattern as #5's `web-deploy.yml` destroy path. Real teardown happens via `make` locally with operator credentials. |
