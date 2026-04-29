# API 5xx Spike

**Symptom.** Email from `news-alerts-prod`: `news-api-prod-5xx` is in `ALARM` state (≥5 5XX responses in 5min). Frontend may be returning blank pages or stale data.

## Triage (first 2 min)

```sh
# Last 10 minutes of API Lambda logs
make api-logs SINCE=10m

# Healthz check — is the Lambda alive at all?
make api-invoke

# Recent deploys to api?
gh run list --workflow=lambda-deploy.yml --limit 5 | grep -i api
```

## Diagnose

| Symptom in logs | Likely cause | Confirm |
|---|---|---|
| `RuntimeError: ... attached to a different loop` | asyncio loop / cached engine bug regression | Check for `news_db.engine.reset_engine()` at top of `lambda_handler.handler` |
| `httpx.HTTPStatusError` from JWKS fetch | Clerk JWKS endpoint timeout/outage | Curl the Clerk issuer directly: `curl -I https://<clerk-issuer>/.well-known/jwks.json` |
| `asyncpg.exceptions.TooManyConnectionsError` | DB pool exhausted | Check Supabase dashboard connection count; restart Lambda if pool stuck |
| `TypeError: ... NoneType` | Missing env var (most often `CLERK_ISSUER` or `SUPABASE_DB_URL`) | `aws lambda get-function-configuration --function-name news-api-prod --profile aiengineer` |
| `mangum.exceptions.UnexpectedMessage` | ASGI translation bug | Recent Mangum upgrade? Check `pyproject.toml` history |
| `Task timed out after Xs` | Lambda timeout too low for the request | API Gateway dashboard p99 latency; bump `var.timeout` in `infra/api/variables.tf` |
| `401 Unauthorized` 5xx-ing in disguise (mapped to 5xx) | This shouldn't happen — 401 is a 4xx | Confirm via API Gateway access logs |

## Remediate

**Roll back deploy:**

```sh
# Find the previous green deploy
gh run list --workflow=lambda-deploy.yml --limit 10 | grep success | head -2

# Roll back via tag
git checkout api-v0.5.0   # or last known-good tag
make api-deploy  # local-direct, faster than CI workflow
```

**Hotfix env var:**

```sh
aws ssm put-parameter --name "/news-aggregator/prod/clerk_issuer" --value "..." \
  --type SecureString --overwrite --profile aiengineer
# Lambda picks up new SSM value on next cold start; force restart:
aws lambda update-function-configuration --function-name news-api-prod \
  --environment "Variables={FORCE_RESTART=$(date +%s)}" --profile aiengineer
```

**Restart the asyncio loop / DB pool:**

If `RuntimeError: ... attached to a different loop` is in logs, the cached `AsyncEngine` is bound to a stale loop. Fix is in code (add `reset_engine()` to handler top); deploy. Short-term: force a Lambda update to recycle warm containers.

## Postmortem

5xx spikes affecting >5 min of user-facing traffic warrant a postmortem under `docs/postmortems/YYYY-MM-DD-api-5xx.md`.
