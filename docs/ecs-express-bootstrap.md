# ECS Express — One-time bootstrap (until #6 lands)

Sub-project #6 owns Terraform for everything AWS. Until it lands, deploying
`services/scraper` to AWS requires a one-time manual bring-up. Everything below
will be codified in #6 as a Terraform module.

All commands assume `AWS_PROFILE=aiengineer`.

## 1. ECR repository

```sh
aws ecr create-repository \
  --profile aiengineer \
  --repository-name news-scraper \
  --image-scanning-configuration scanOnPush=true
```

Once created, `services/scraper/deploy.py --mode build` can push images.

## 2. IAM roles (required by ECS Express)

Per the [AWS ECS Express service overview](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html),
Express Mode needs two roles:

- **Task execution role** — pulls from ECR, writes CloudWatch logs.
- **Infrastructure role** — manages ECS-owned AWS resources (ALB target group,
  service-linked networking).

Create both using the AWS console (IAM → Roles → Create role → pick ECS
trust templates) or CLI — document whichever ARN you end up with.

Capture both ARNs in a scratch file; you'll paste them into #6's Terraform
variables file when it lands.

## 3. ECS Express service

Through the AWS console:
- Create cluster `news-aggregator` (Fargate, default VPC or a pre-existing one).
- Create an ECS Express service pointing at
  `<account>.dkr.ecr.<region>.amazonaws.com/news-scraper:latest` on port 8000.
- Health check path: `/healthz`.
- Attach the two IAM roles from step 2.
- Wire environment variables from Supabase, OpenAI, Langfuse — same names as
  `.env.example`.

## 4. Smoke

```sh
curl https://<service-url>/healthz
# expect: {"status":"ok","git_sha":"<hash>"}

curl -X POST https://<service-url>/ingest \
  -H 'content-type: application/json' \
  -d '{"lookback_hours":6}'
# expect: 202 { "id":"...", "status":"running", ... }
```

## 5. Retiring this doc

When #6 ships, this file becomes historical context. Delete or move to
`docs/archive/` at that time.
