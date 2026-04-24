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
# runs: docker build -> docker push -> terraform apply -replace=... -> smoke /healthz
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
