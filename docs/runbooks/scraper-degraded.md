# Scraper Degraded

**Symptom.** Cron pipeline alarm fires (`news-cron-pipeline-failed-prod`) AND the Step Functions execution history shows `TriggerScraper` or `PollScraper` as the failing stage. Or: the scraper service has been at 0 healthy tasks for >10 minutes.

## Triage (first 2 min)

```sh
# Service state — desired count, running count, healthy hosts
make scraper-status

# Last 30 min of scraper logs
make scraper-logs SINCE=30m

# ECS service events (deployment history, task placement failures)
aws ecs describe-services \
  --cluster $(cd infra/scraper && terraform output -raw cluster_name) \
  --services news-scraper-prod \
  --query 'services[0].events[0:10]' \
  --profile aiengineer
```

## Diagnose

| Symptom | Likely cause | Confirm |
|---|---|---|
| ECS task crash-looping (`runningCount=0`, `pendingCount=1` flipping) | OOM (Playwright + Chromium memory > task memory) | CloudWatch container insights memory; bump `var.task_memory` in `infra/scraper/variables.tf` |
| Logs show Playwright child crashes | rss-mcp / Playwright MCP version drift | Check `services/scraper/Dockerfile` for `@playwright/mcp@latest` floating tag — pin a specific version |
| Logs show 429 from external sites | Rate-limited by source (Anthropic/OpenAI/etc. blog) | Reduce concurrency in `services/scraper/src/news_scraper/sources.yml` |
| Logs OK but `/runs/:id` returns 404 to SFN | Run state lost after task recycled | Check ECS `serviceConnectConfiguration`; consider keeping task warm during runs (`make scraper-pin-up` during business hours) |
| ECR image won't pull | Latest image tag corrupted by previous failed push | `aws ecr describe-images --repository-name news-scraper-prod` — re-tag a known-good image |
| ALB / endpoint not resolving | DNS or service-discovery issue | `dig $(cd infra/scraper && terraform output -raw service_url)` |

## Remediate

**Force a redeploy of latest image:**

```sh
make scraper-redeploy
```

**Pin warm during repro:**

```sh
make scraper-pin-up
# ...repro and gather logs...
make scraper-pin-down   # restore autoscaling + scale-to-zero
```

**Roll back to previous image:**

```sh
# Find the prior green tag in ECR
aws ecr describe-images --repository-name news-scraper-prod \
  --query 'sort_by(imageDetails,&imagePushedAt)[-3:].[imageTags[0],imagePushedAt]' \
  --output text --profile aiengineer

# Re-tag desired SHA as latest (manual)
aws ecr batch-get-image --repository-name news-scraper-prod --image-ids imageTag=<SHA> \
  --query 'images[0].imageManifest' --output text --profile aiengineer > /tmp/m.json
aws ecr put-image --repository-name news-scraper-prod --image-tag latest \
  --image-manifest "$(cat /tmp/m.json)" --profile aiengineer

make scraper-redeploy
```

**Bump task memory (recurring OOM):**

Edit `infra/scraper/variables.tf` — bump `var.task_memory` from `2048` to `4096`. Then `make scraper-deploy-ci ENV=prod` (workflow_dispatch).

## Postmortem

Required if scraper outage prevented a full daily digest cycle. Capture under `docs/postmortems/YYYY-MM-DD-scraper-degraded.md`.
