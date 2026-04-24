# ECS Express — historical notes

Terraform (in [`infra/scraper/`](../infra/scraper/)) now owns the ECR repo,
ECS cluster, IAM roles, SSM params, and the ECS Express service itself. Nothing
here needs to be done manually. Bring-up walkthrough is in
[`infra/README.md`](../infra/README.md).

Two things this doc captured originally are still true but are now the
*only* manual prerequisites before running `make tf-scraper-init`:

1. An AWS account with the `aiengineer` IAM user (or adjust `aws_profile`).
2. A Route53 hosted zone for `patrickcmd.dev` (used by future sub-projects for
   public-facing API / frontend subdomains; the scraper itself uses the
   auto-provisioned ECS Express endpoint and needs no DNS).

Everything else — IAM permissions, ECR repo, cluster, service, logs, secrets —
is Terraform.
