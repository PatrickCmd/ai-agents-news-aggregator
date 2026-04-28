# Cron Pipeline Failure

**Symptom.** Email from `news-alerts-prod` SNS topic: `news-cron-pipeline-failed-prod` or `news-cron-pipeline-stale-prod` is in `ALARM` state. No daily digest emails went out.

## Triage (first 2 min)

```sh
# Last 5 cron pipeline executions
make cron-history

# Most recent failure: full state-by-state trace
EXEC=$(aws stepfunctions list-executions \
  --state-machine-arn $(cd infra/scheduler && terraform workspace select prod >/dev/null && terraform output -raw cron_state_machine_arn) \
  --status-filter FAILED --max-items 1 \
  --profile aiengineer --query 'executions[0].executionArn' --output text)
make cron-describe NAME="$EXEC"

# Recent GitHub Actions deploys that may correlate
gh run list --workflow=lambda-deploy.yml --limit 5
```

The Step Functions execution history shows which stage failed: `TriggerScraper`, `WaitForScraper`/`PollScraper`, `DigestMap`, `EditorMap`, `EmailMap`, or one of the list ops.

## Diagnose

| Stage | Likely cause | Confirm |
|---|---|---|
| `TriggerScraper` http:invoke | Scraper service is down / cold-starting / rate-limited | `make scraper-status`; check ECS service desired-count + healthy task count |
| `PollScraper` cap hit (60×30s) | Scraper run took longer than 30 minutes | Scraper logs: `make scraper-logs SINCE=1h`; look for stuck Playwright child process |
| `DigestMap` failures (silent — `ToleratedFailurePercentage=100`) | OpenAI quota / API outage / asyncio loop bug regression | `make agents-logs AGENT=digest SINCE=1h`; Langfuse trace for failed article IDs |
| `EditorMap` failures | Same as digest, plus user-profile misformat | `make agents-logs AGENT=editor SINCE=1h` |
| `EmailMap` failures | Resend rate-limit (free tier = 2/sec) or Resend API outage | Email Lambda logs; Resend dashboard |
| `cron_stale-36h` only (no `cron_failed`) | EventBridge cron rule disabled or paused | `aws events list-rules --name-prefix news-cron --profile aiengineer` |

## Remediate

**Re-run after fix:**

```sh
make cron-invoke   # one-off pipeline run, doesn't wait for the next 21:00 UTC tick
```

**Per-stage fixes:**

- **Scraper down:** `make scraper-pin-up` to keep service warm at desired-count=1 during repro; `make scraper-redeploy` to force pull the latest image. If still failing, redeploy from main: `make scraper-deploy-ci ENV=prod` (workflow_dispatch).
- **Digest/Editor/Email errors:** check Langfuse for the actual prompt/completion that failed. If OpenAI quota: wait or upgrade tier. If asyncio loop bug regressed: confirm `news_db.engine.reset_engine()` is at the top of the failed Lambda's handler (decision #6 in README; this bit us before).
- **Resend rate-limit:** `EmailMap` already runs at MaxConcurrency=2. If still hitting limits, consider upgrading to a paid Resend tier (out of scope for #6).
- **EventBridge cron disabled:** re-enable via `aws events enable-rule --name news-cron-prod --profile aiengineer`.

**Roll back deploy that introduced the regression:**

If a recent `lambda-deploy` correlates: re-run with the previous git SHA's tag. Example: `git checkout agents-v0.3.0 && make lambda-deploy SERVICE=digest ENV=prod`.

## Postmortem

If the incident exceeded 2 hours or affected actual delivered emails:

```sh
mkdir -p docs/postmortems
cp docs/runbooks/_postmortem-template.md \
   docs/postmortems/$(date +%Y-%m-%d)-cron-pipeline-failure.md
```

Capture: timeline, root cause, customer impact, fix applied, prevention work.
