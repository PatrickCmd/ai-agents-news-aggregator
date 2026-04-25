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
