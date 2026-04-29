# Infrastructure (Terraform)

Per-sub-project Terraform root modules. Each deployable owns its own
`infra/<name>/` dir, independently applied, sharing a common remote-state
backend.

## Conventions

- **One root module per deployable.** `infra/scraper/` today; later
  `infra/agents/`, `infra/api/`, `infra/frontend/`, `infra/scheduler/`.
- **Remote state:** S3 bucket `news-aggregator-tf-state-<account-id>` with S3
  native locking (`use_lockfile=true`), created once by `infra/bootstrap/`.
- **Per-env separation:** Terraform workspaces (`dev`, `prod`), not duplicated
  directories.
- **AWS auth:** `AWS_PROFILE=aiengineer` (default). Override with
  `export AWS_PROFILE=<other>`.
- **IAM permissions for aiengineer:** granted by the two groups created by
  [`infra/setup-iam.sh`](setup-iam.sh) — `NewsAggregatorCoreAccess` (scraper)
  and `NewsAggregatorComputeAccess` (future sub-projects).
- **Secrets:** live in SSM Parameter Store (SecureString). Pushed via
  `sync_secrets.py`, not Terraform.

## One-time bootstrap

Creates the state bucket. Run once, ever.

```sh
# IAM setup — only the first time, or to re-sync user -> group memberships.
# Uses an admin profile like 'patrickcmd' to create groups and attach the
# aiengineer user. The script is idempotent.
ADMIN_PROFILE=patrickcmd ./infra/setup-iam.sh

# Terraform state backend
make tf-bootstrap
# Records state_bucket_name, account_id in Terraform output.
```

Bootstrap uses **local state** (gitignored) — it can't depend on the backend
it's creating. If the local state file is lost, recover with:

```sh
cd infra/bootstrap
terraform import aws_s3_bucket.tf_state news-aggregator-tf-state-<account-id>
terraform import aws_dynamodb_table.tf_lock news-aggregator-tf-locks
```

## Scraper module

First-time initialization:

```sh
make tf-scraper-init STATE_BUCKET=news-aggregator-tf-state-<account>
cd infra/scraper
terraform workspace new dev   # or `terraform workspace select dev`
terraform apply               # creates ECR, cluster, IAM, SSM, service
make secrets-sync ENV=dev     # push real .env values into SSM
```

Subsequent deploys (build new image + roll the service):

```sh
make scraper-deploy
# runs: docker build -> docker push -> terraform apply -> smoke /healthz
```

## Day-to-day operations

| Task | Command |
|---|---|
| Show service state | `make scraper-status` |
| Pin service up for active testing (no auto-scale-in) | `make scraper-pin-up` |
| Restore cost-saving mode (autoscaling on, scale to 0) | `make scraper-pin-down` |
| Drain to 0 quickly without touching autoscaling | `make scraper-pause` |
| Bring back to 1 | `make scraper-resume` |
| Re-roll the running task with the latest `:latest` image | `make scraper-redeploy` |
| Push code change + roll | `make scraper-deploy` |

### Live endpoint testing

| Task | Command |
|---|---|
| Health check | `make scraper-test-health` |
| Trigger all 3 pipelines | `make scraper-test-ingest LOOKBACK=6` |
| Trigger RSS only (cheapest) | `make scraper-test-ingest-rss LOOKBACK=6` |
| Trigger YouTube only | `make scraper-test-ingest-youtube LOOKBACK=24` |
| Trigger web-search only (LLM-cost) | `make scraper-test-ingest-web LOOKBACK=48` |
| List recent runs | `make scraper-test-runs` |
| Show one run by id | `make scraper-test-run RUN_ID=<uuid>` |
| Tail CloudWatch logs (last 5 min) | `make scraper-logs SINCE=5m` |
| Follow CloudWatch logs live | `make scraper-logs-follow` |

`LOOKBACK` defaults to 6 hours. `SINCE` accepts AWS-CLI relative-time strings (e.g., `30m`, `2h`).

Typical interactive flow:

```sh
make scraper-pin-up                       # keep service warm
make scraper-test-ingest-rss LOOKBACK=3   # trigger small RSS run
# capture run id from response, then:
make scraper-test-run RUN_ID=<uuid>       # poll until status=success/partial
make scraper-test-runs                    # list recent
make scraper-pin-down                     # back to cost mode
```

**For interactive smoke tests:** use `scraper-pin-up` not `scraper-resume`. With autoscaling enabled, `min_capacity=0` plus low request count causes the autoscaler to drain your task back to 0 ~5 minutes after the last request — your follow-up `curl` then 503s. `pin-up` suspends the autoscaler so the task stays warm until you `pin-down`.

## Recovery from common errors

### `Provider produced inconsistent result after apply`

ECS Express auto-attaches a security group that the provider didn't predict in plan. Resource is **created in AWS** but flagged tainted in Terraform state. Fix:

```sh
make scraper-recover
# untaints + reapplies. Outputs (scraper_endpoint) populate after this.
```

### `Express Gateway Service ... already exists in cluster`

You ran a destroy+create (e.g., via `-replace`) but AWS retains the INACTIVE service record for ~1 hour, blocking name reuse. Either wait, or rename in `service.tf` (e.g., `scraper-${terraform.workspace}-2`).

### `ParameterAlreadyExists` on SSM params

The 8 SSM params exist in AWS but Terraform state lost track (e.g., after a partial destroy or running `make secrets-sync` outside Terraform). Fix:

```sh
make scraper-import-secrets
# imports all 8 params into Terraform state; idempotent.
```

### Fresh-start (after `make scraper-destroy`)

```sh
make scraper-bootstrap        # ECR + cluster + IAM + SSM + logs (everything but the service)
make secrets-sync ENV=dev     # push real .env values into SSM
make scraper-deploy           # build + push image + create service
```

## Adding a new sub-project module

1. `mkdir infra/<name>`
2. Copy `infra/scraper/backend.tf` and adjust the backend `key` to
   `<name>/terraform.tfstate` (unique per module in the shared bucket).
3. Write module-specific Terraform.
4. `terraform init -backend-config=...` (same bucket, different `key`).
5. Same workspace pattern (`dev`/`prod`).

If the sub-project needs additional AWS services beyond the policies in
`setup-iam.sh`, update the policy list in that script and re-run it.

## Sub-project #2 — agents (digest / editor / email Lambdas)

Three independent AWS Lambda functions, each shipped as a zip artifact in S3
and managed by its own Terraform module under `infra/{digest,editor,email}/`.

### One-time bootstrap extension

Phase 2 of sub-project #2 added an `aws_s3_bucket.lambda_artifacts` resource
to the bootstrap module. If you re-init bootstrap state on a fresh machine,
ensure the bucket already exists (or re-apply bootstrap):

```sh
cd infra/bootstrap && terraform apply
```

The bucket is `news-aggregator-lambda-artifacts-<account_id>`.

### Per-agent Terraform init

Each module reads the artifact bucket name inline (computed from
`data.aws_caller_identity.current.account_id`) — no remote-state coupling.
Init each module once with the right state-key:

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
for agent in digest editor email; do
  cd infra/$agent
  terraform init \
    -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
    -backend-config="key=$agent/terraform.tfstate" \
    -backend-config="region=us-east-1" \
    -backend-config="profile=aiengineer"
  cd -
done
```

### Deploy

`deploy.py` per agent builds the zip, uploads to S3, and runs `terraform
apply`. Email requires `MAIL_FROM` (Resend-verified sender domain):

```sh
make digest-deploy
make editor-deploy
MAIL_FROM=hi@yourdomain.com make email-deploy
```

Each agent's first deploy creates 5 resources: IAM role + 2 policy
attachments + log group + Lambda function.

### Invoke + logs

```sh
make digest-invoke ARTICLE_ID=42
make editor-invoke USER_ID=<uuid>
make email-invoke DIGEST_ID=17

make agents-logs AGENT=digest SINCE=10m
make agents-logs-follow AGENT=email
```

### Roll back

To redeploy a previous version, `terraform apply` with the previous zip's
S3 key + sha256 (look them up in `s3://news-aggregator-lambda-artifacts-*/<agent>/`):

```sh
cd infra/digest
terraform apply -var=zip_s3_key=digest/<previous-sha>.zip -var=zip_sha256=<previous-base64-sha256>
```

To destroy a single agent (preserves the artifact bucket):

```sh
cd infra/<agent>
terraform destroy -var=zip_s3_key=anything -var=zip_sha256=anything
```

(Required vars must be set — values don't matter on destroy.)

### IAM scope

Each Lambda's role has read access to `arn:aws:ssm:...:parameter/news-aggregator/<env>/*`
(SSM SecureStrings populated by sub-project #1) plus AWSLambdaBasicExecutionRole
for CloudWatch logs. No cross-account permissions, no shared state with the
scraper service.

### Failure modes

- **Lambda zip > 50 MB** — direct upload limit. Currently ~39 MB per agent;
  monitor when adding deps.
- **`MAIL_FROM` rejected by Resend** — domain not verified. Add it at
  https://resend.com/domains.
- **`make agents-logs SINCE=...` shows no entries** — Lambda hasn't been
  invoked yet, or the function name is wrong (must match `news-<agent>-dev`).
- **Cold-start SSM read fails** — SSM params missing for the env. Re-run
  `make secrets-sync ENV=dev` (from sub-project #1).

## Sub-project #3 — scheduler + orchestration

A scheduler Lambda (`news-scheduler-dev`) plus two AWS Step Functions state
machines that orchestrate the end-to-end pipeline:

- **`news-cron-pipeline-dev`** — daily fan-out triggered by an EventBridge
  rule at `cron(0 21 * * ? *)` (00:00 EAT). Steps: `TriggerScraper` (HTTP) →
  poll `/runs/<id>` until terminal → `ListUnsummarised` → `DigestMap` →
  `ListActiveUsers` → `EditorMap` → `ListNewDigests` → `EmailMap`. Maps run
  with `ToleratedFailurePercentage=100` so per-item failures don't fail the
  whole pipeline.
- **`news-remix-user-dev`** — single-user "remix my digest now" — invokes
  the editor Lambda for a given user, and if a new digest was generated,
  invokes the email Lambda. Triggered manually (later wired to the web UI
  in sub-project #4).

The scheduler Lambda itself is dispatched by `event["op"]` to one of three
list handlers (`list_unsummarised`, `list_active_users`, `list_new_digests`)
that read directly from the database.

### One-time IAM extension

Sub-project #3 adds `AWSStepFunctionsFullAccess` and `CloudWatchFullAccess`
to the `NewsAggregatorComputeAccess` group. If you bootstrapped before April
2026, re-run:

```sh
ADMIN_PROFILE=patrickcmd ./infra/setup-iam.sh
```

### Per-module Terraform init

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/scheduler
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=scheduler/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
terraform workspace new dev   # or: terraform workspace select dev
```

### Deploy

`services/scheduler/deploy.py` builds the zip (via `package_docker.py`),
uploads to S3, reads the scraper's HTTPS endpoint from
`infra/scraper`'s Terraform output, then runs `terraform apply`:

```sh
make scheduler-deploy
```

First apply creates ~13 resources: Lambda + IAM role + 2 SFN state machines
(with their IAM roles, log groups, EventBridge connection) + EventBridge
cron rule + 2 CloudWatch alarms (`cron-failed`, `cron-stale-36h`).

### Invoke + monitor

```sh
make cron-invoke                              # one-off cron run
make cron-history                             # last 5 executions
make cron-describe NAME=<exec-name>           # full state-by-state trace

make remix-invoke USER_ID=<uuid> LOOKBACK=24  # send my digest now
make remix-history

make scheduler-logs SINCE=10m                 # scheduler Lambda logs
make scheduler-logs-follow

# Local CLI (talks to DB directly, no Lambda):
make scheduler-list-unsummarised LOOKBACK=24
make scheduler-list-active-users
make scheduler-list-new-digests
```

### Failure modes

- **`Events.ConnectionResource.AccessDenied`** on `TriggerScraper` — the
  cron state machine's IAM role is missing `secretsmanager:DescribeSecret`
  (or `:GetSecretValue`) on the EventBridge Connection's auto-created
  secret. Both are required.
- **`States.Http.StatusCode.422`** on `TriggerScraper` — the ASL's request
  body doesn't match the scraper's `IngestRequest` schema. The `trigger`
  field must be one of `api|cli|scheduler` (the cron pipeline sends
  `"scheduler"`).
- **`RuntimeError: ... attached to a different loop`** in any Lambda — a
  warm-start container has a cached SQLAlchemy engine bound to a previous
  event loop. The handlers call `news_db.engine.reset_engine()` at the top
  of every invocation; if you add a new Lambda, do the same.
- **`ListActiveUsers` returns `[]`** — no users have `profile_completed_at
  IS NOT NULL`. In dev, re-run `make seed`; in prod, this is set by the
  Clerk-driven onboarding flow (sub-project #4).
- **`ScraperPollTimeout`** — scraper run did not reach `success`/`partial`/
  `failed` within `scraper_poll_max_iterations × 30s` (default 30 min).
  Investigate the scraper directly: `make scraper-logs SINCE=30m`.

### Roll back

The cron + remix state-machine definitions live in
`infra/scheduler/templates/*.asl.json` — to roll back a definition change,
revert the file and `terraform apply` (no zip upload needed). To roll back
the Lambda code, follow the same pattern as sub-project #2:

```sh
cd infra/scheduler
terraform apply \
  -var=zip_s3_key=scheduler/<previous-sha>.zip \
  -var=zip_sha256=<previous-base64-sha256> \
  -var=scraper_base_url=https://$(cd ../scraper && terraform output -raw scraper_endpoint)
```

## Sub-project #4 — API + Auth

A `news-api-dev` Lambda fronted by an API Gateway HTTP API exposing six
endpoints (`/v1/healthz`, `/v1/me`, `/v1/me/profile`, `/v1/digests`,
`/v1/digests/{id}`, `/v1/remix`). Validates Clerk JWTs in a FastAPI
dependency, lazy-creates user rows on first call, and triggers the
remix state machine (#3) for on-demand digest re-runs.

### One-time IAM extension

**None.** `NewsAggregatorComputeAccess` already grants
`AWSLambda_FullAccess`, `AmazonAPIGatewayAdministrator`, and
`AmazonS3FullAccess` — those cover everything `infra/api/` provisions.

### Per-module Terraform init

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/api
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=api/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
terraform workspace new dev   # or: terraform workspace select dev
```

### SSM secret seed

```sh
aws ssm put-parameter \
  --name /news-aggregator/dev/clerk_secret_key \
  --value "<your-clerk-secret-key>" \
  --type SecureString \
  --overwrite \
  --profile aiengineer
```

`clerk_publishable_key` is **not** stored in SSM — it's, by definition,
public, and lives in the Next.js frontend's env file (#5).

### Deploy

```sh
export CLERK_ISSUER=https://<your-clerk-frontend-api>
export ALLOWED_ORIGINS=http://localhost:3000
make api-deploy
```

First apply creates ~10 resources: Lambda + IAM role + 2 policy attachments
+ log group + HTTP API + stage + integration + route + Lambda permission +
access log group + 5xx alarm.

### Invoke + monitor

```sh
make api-invoke                          # smoke /v1/healthz
make api-test-me JWT=<real-clerk-jwt>    # GET /v1/me with a JWT you minted

# Full end-to-end smoke — mints its own JWT via Clerk Backend API, hits all
# four authenticated endpoints, optionally triggers a remix run. Requires
# a `news-api` JWT template in Clerk Dashboard with email + name claims
# and ≥120s lifetime; see scripts/api-smoke.sh header for setup.
USER_ID=user_xxx make api-smoke                # full smoke
USER_ID=user_xxx SKIP_REMIX=1 make api-smoke   # skip the SFN run

make api-logs SINCE=10m                  # tail Lambda logs
make api-logs-follow

# Local dev (no AWS):
make api-serve
```

### Failure modes

- **`401 invalid token` in dev** — your `CLERK_ISSUER` env var points at
  a different Clerk instance than the one minting your JWT. Inspect the
  deployed config:
  `aws lambda get-function-configuration --function-name news-api-dev
  --query 'Environment.Variables' --profile aiengineer`.
- **`401 missing bearer token` from the frontend** — CORS preflight
  passing but the actual fetch missing `Authorization` header.
- **`AccessDenied` on remix `start_execution`** — the API role's IAM
  is scoped to the *exact* remix ARN read via
  `terraform_remote_state.scheduler`. If you re-applied the scheduler
  with a different workspace, the API's stored ARN may be stale —
  re-run `terraform apply` on the API module.
- **`RuntimeError: ... attached to a different loop`** — the
  `reset_engine()` call at the top of `handler()` was removed or
  bypassed. Re-add it (see #2/#3 anti-pattern).
- **CORS preflight 404s** — `var.allowed_origins` doesn't include the
  caller's origin. Update and re-apply.

### Roll back

To roll back the Lambda code:

```sh
cd infra/api
terraform apply \
  -var=zip_s3_key=api/<previous-sha>.zip \
  -var=zip_sha256=<previous-base64-sha256> \
  -var=git_sha=<previous-sha> \
  -var=clerk_issuer=https://<your-clerk-frontend-api>
```

To destroy the API module entirely (keeps the artefact bucket, the
scheduler, and all state):

```sh
cd infra/api
terraform destroy -var=zip_s3_key=anything -var=zip_sha256=anything \
  -var=git_sha=anything -var=clerk_issuer=https://placeholder.example.com
```

## Sub-project #5 — Frontend (Next.js + Clerk + S3/CloudFront)

A static-exported Next.js app served from CloudFront, fronted by ACM cert
on `*.patrickcmd.dev`, with one CloudFront distribution + S3 bucket per
environment (dev/test/prod). Auth via Clerk's hosted Account Portal;
data via the API shipped in #4.

### Prerequisites (one-time)

1. **GitHub Actions OIDC provider** in the AWS account — created in
   `infra/bootstrap/`. Re-apply bootstrap if it doesn't exist:
   ```sh
   cd infra/bootstrap && terraform apply
   ```

2. **ACM wildcard cert** `*.patrickcmd.dev` in us-east-1 (existing).
   Verify:
   ```sh
   aws acm list-certificates --region us-east-1 --profile aiengineer \
     --query 'CertificateSummaryList[].DomainName' --output text
   ```

3. **Route 53 hosted zone** for `patrickcmd.dev` (existing).

4. **GitHub Environments** — `dev`, `test`, `prod` set up under repo
   Settings → Environments. Each gets vars + secrets (see "GitHub
   Environment configuration" below).

### Per-module Terraform init + apply

Per-environment:

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/web
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=web/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"

# For dev (repeat for test, prod with the matching subdomain):
terraform workspace new dev
terraform apply \
  -var=subdomain=dev-digest.patrickcmd.dev \
  -var=github_repo=PatrickCmd/ai-agents-news-aggregator
```

First apply creates ~10 resources: S3 bucket + 3 sub-resources +
bucket policy + CloudFront + OAC + 2 Route 53 records + GitHub OIDC
IAM role + policy.

### GitHub Environment configuration

Per env, set (via GitHub Settings → Environments → `<env>`):

**Vars (non-secret):**
- `AWS_DEPLOY_ROLE_ARN` — Terraform output `gh_actions_role_arn`
- `AWS_ACCOUNT_ID` — your AWS account ID
- `NEXT_PUBLIC_API_URL` — backend API base URL for that env
- `S3_BUCKET` — Terraform output `bucket_name`
- `CLOUDFRONT_DISTRIBUTION_ID` — Terraform output `distribution_id`
- `SUBDOMAIN` — full subdomain for that env

**Secrets:**
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` — from Clerk Dashboard

**Required reviewers:** add at least one for `prod`. Skip for dev/test.

### Deploy + destroy

```sh
make web-deploy-dev          # workflow_dispatch → deploy to dev
make web-deploy-test
make web-deploy-prod         # gated by reviewer

make web-destroy-dev         # workflow_dispatch → terraform destroy dev
make web-destroy-test
make web-destroy-prod        # use VERY carefully
```

### Failure modes

- **Build fails: `process is not defined`** — used a Node-only API in a
  client component. Audit imports; only browser-safe code allowed in
  static export.
- **Deploy succeeds but page returns 403** — bucket policy missing or
  OAC not bound. Re-apply Terraform.
- **CloudFront serves stale HTML after deploy** — invalidation didn't
  fire. Manually: `aws cloudfront create-invalidation --distribution-id
  <id> --paths '/*' --profile aiengineer`.
- **`401 invalid token` from API on every request** — `NEXT_PUBLIC_API_URL`
  env var doesn't match the deployed API's `CLERK_ISSUER`. Or the
  Clerk publishable key is for a different instance than the API expects.
- **`Cannot read 'getToken' of undefined`** — `<ClerkProvider>` not
  rendered above the consuming component. Check `app/providers.tsx`.
- **JWT template missing email/name claims** — frontend uses
  `getToken({ template: "news-api" })`. The template must exist in
  Clerk Dashboard → JWT Templates with email + name claims (same
  template the backend's smoke uses — see #4 spec §3).
- **Workflow fails with `AssumeRoleWithWebIdentity` AccessDenied** —
  the job is missing `environment: <name>` at the job level. The OIDC
  IAM role's sub-claim restricts AssumeRole to
  `repo:<owner>/<name>:environment:{env}` — without the key it fails.

### Roll back

To roll back the static bundle:

```sh
# S3 versioning is enabled on the bucket; restore prior versions via:
aws s3api list-object-versions --bucket digest-dev-dev-digest-patrickcmd-dev \
  --profile aiengineer

# Promote a prior version manually, then invalidate CloudFront.
```

To destroy a single env entirely (keeps Route 53 zone, ACM cert, OIDC provider):

```sh
make web-destroy-dev
```

## Sub-project #6 — CI/CD + Ops

`infra/alerts/` owns the per-env SNS topic + (prod-only) email subscription + SSM parameter publishing the topic ARN. Every per-service alarm reads the SSM parameter via `data.aws_ssm_parameter.alerts_arn` and wires `alarm_actions = [data.aws_ssm_parameter.alerts_arn.value]`. SNS subscription confirmation in prod requires clicking the AWS confirmation email (one-time, after first apply).

### Apply order (first-time bootstrap of #6)

```sh
# 1. Alerts module — must be applied first (other modules read its SSM param).
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/alerts
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=alerts/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
terraform workspace new dev    # repeat for test, prod
terraform apply
cd -

# 2. Re-apply each service module — adds OIDC role + alarms (no destructive changes).
for svc in digest editor email scheduler api scraper; do
  cd "infra/$svc"
  terraform workspace select dev
  terraform apply
  cd -
done
```

### GitHub Environment configuration

For each env (`dev`, `test`, `prod`), set Settings → Environments → `<env>` → Variables:

- `AWS_ACCOUNT_ID` — your AWS account ID
- `AWS_DEPLOY_ROLE_ARN` — Terraform output `gh_actions_role_arn` from `infra/scraper/`
- `AWS_DEPLOY_ROLE_ARN_digest` — same from `infra/digest/`
- `AWS_DEPLOY_ROLE_ARN_editor` — from `infra/editor/`
- `AWS_DEPLOY_ROLE_ARN_email` — from `infra/email/`
- `AWS_DEPLOY_ROLE_ARN_scheduler` — from `infra/scheduler/`
- `AWS_DEPLOY_ROLE_ARN_api` — from `infra/api/`

> `format()` in `lambda-deploy.yml` produces lowercase suffixes (e.g. `AWS_DEPLOY_ROLE_ARN_digest`). Use lowercase names exactly as listed.

For `prod` only:
- Required reviewer (Settings → Environments → `prod` → Required reviewers)

### Trigger deploys

```sh
make scraper-deploy-ci ENV=dev                    # workflow_dispatch
make lambda-deploy SERVICE=digest ENV=dev         # workflow_dispatch
gh run watch                                      # tail latest run
```

### Alarm verification

After applying alerts to prod and confirming the SNS subscription email:

```sh
aws sns publish \
  --topic-arn $(cd infra/alerts && terraform workspace select prod >/dev/null && terraform output -raw alerts_topic_arn) \
  --message "test from cicd-ops-v0.8.0 verification" \
  --profile aiengineer
```

Confirm email lands.

### Failure modes

- **`AssumeRoleWithWebIdentity` AccessDenied.** The workflow job is missing `environment: <env>` or the GitHub Environment doesn't exist or the role's `sub` claim doesn't match. Verify the workflow has `environment: ${{ inputs.environment }}` at the JOB level.
- **`alarm_actions` not firing in prod.** SNS subscription not yet confirmed — check the inbox of `var.alert_email` for the AWS confirmation email and click "Confirm subscription".
- **Per-Lambda alarm in `INSUFFICIENT_DATA`.** `treat_missing_data = "notBreaching"` keeps it green when there's no traffic. Force an error to verify wiring (see `docs/runbooks/cron-pipeline-failure.md`).
- **Terraform apply on alerts fails with `aws_sns_topic_subscription` empty endpoint.** You're applying `prod` workspace without setting `alert_email` in `terraform.tfvars`. Set it.
