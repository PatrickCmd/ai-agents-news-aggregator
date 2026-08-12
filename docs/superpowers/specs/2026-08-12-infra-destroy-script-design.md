# infra-destroy script — design

**Date:** 2026-08-12
**Status:** approved
**Scope:** `scripts/infra-destroy.sh` + one Makefile target

## Problem

Local teardown exists only for `web` (`make web-destroy-dev-local`); every other
infra module (alerts, api, digest, editor, email, scheduler, scraper) has no
scripted destroy path. The CI OIDC roles are deliberately too narrow to run
`terraform destroy`, so teardown must run locally with full access
(`AWS_PROFILE=aiengineer`).

## Interface

```
scripts/infra-destroy.sh [--env dev|test|prod] [--profile aiengineer] [--yes] <service ...|all>
```

- **Services:** `alerts api digest editor email scheduler scraper web`.
  `bootstrap` is rejected with an explanatory error — it holds the Terraform
  state bucket + lock table and stays a manual, local-state operation.
- **`--env`** (default `dev`) selects the Terraform workspace in each module.
  A module without that workspace is skipped with a note.
- **`all`** expands, in reverse-dependency order:
  `api → scheduler → email → editor → digest → scraper → web → alerts`
  (api reads scheduler's outputs via `terraform_remote_state`, so it goes
  first; every module's alarms read the alerts SSM parameter, so alerts goes
  last; `infra/api/main.tf` wraps the scheduler output in `try()` so api can
  still be destroyed even if scheduler is already gone).
- **Makefile:**

  ```make
  infra-destroy:   ## DESTRUCTIVE: destroy infra module(s): SERVICE=<name|all> [ENV=dev]
  	@test -n "$(SERVICE)" || (echo "SERVICE required: e.g. SERVICE=api or SERVICE=all" >&2; exit 1)
  	./scripts/infra-destroy.sh --env $(or $(ENV),dev) $(SERVICE)
  ```

## Per-module behavior

1. `terraform init -backend-config` — state bucket
   `news-aggregator-tf-state-<account-id>` (account id from
   `aws sts get-caller-identity`), key `<module>/terraform.tfstate`, region
   `us-east-1`.
2. `terraform workspace select $ENV` — missing workspace ⇒ skip module.
3. `terraform destroy -auto-approve` with dummy values for required vars
   (values are irrelevant on destroy; they only satisfy validation —
   documented in `infra/README.md`):

   | module    | dummy vars |
   |-----------|------------|
   | api       | `zip_s3_key=anything zip_sha256=anything clerk_issuer=https://placeholder.example.com` |
   | digest    | `zip_s3_key=anything zip_sha256=anything` |
   | editor    | `zip_s3_key=anything zip_sha256=anything` |
   | email     | `zip_s3_key=anything zip_sha256=anything mail_from=placeholder@example.com` |
   | scheduler | `zip_s3_key=anything zip_sha256=anything scraper_base_url=https://placeholder.example.com` |
   | web       | `subdomain=<env-prefix>digest.patrickcmd.dev` (`dev-digest`/`test-digest`/`digest`) |
   | alerts, scraper | none |

4. **BucketNotEmpty retry:** if destroy fails with S3 `BucketNotEmpty`, parse
   the bucket name from the error, purge all object versions + delete markers
   (paginated `list-object-versions` → `delete-objects`), retry destroy once.

## Safety

- One typed confirmation up front, listing env + exact modules:
  type `destroy-<env>`; for prod, `destroy-prod-really`.
- `--yes` skips the prompt (scripted use).
- `set -euo pipefail`; in an `all` run a failing module aborts the run —
  re-running is idempotent (Terraform resumes from remaining state).

## Testing

`bash -n` syntax check; `make -n` dry-run; live checks of `--help`, unknown
service rejection, and `bootstrap` rejection. No real destroy is run as part
of implementation.

## Out of scope

- Destroying `bootstrap` (state bucket) — manual only.
- CI/workflow destroy paths (the OIDC roles can't destroy by design).
- `force_destroy` on versioned buckets (possible future Terraform change).
