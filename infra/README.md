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
