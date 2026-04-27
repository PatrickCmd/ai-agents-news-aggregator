# AI News Aggregator

A multi-source pipeline that ingests YouTube, RSS, and web-search content, summarises each article with an LLM, ranks the top 10 items per user using an editor agent, and sends a personalised daily digest email.

## Current status

**Sub-projects #0 → #3** are implemented and live on AWS.

- **#0 Foundation** ships the `packages/` workspace + schema. Tag `foundation-v0.1.1`.
- **#1 Ingestion** ships `services/scraper/` — a FastAPI + CLI service with three pipelines (YouTube RSS, blog RSS via rss-mcp, web search via Playwright MCP + OpenAI Agents SDK), running on ECS Express. Tag `ingestion-v0.2.1`.
- **#2 Agents** ships three Lambda functions: `news-digest-dev` (per-article LLM summary), `news-editor-dev` (per-user top-10 ranking), `news-email-dev` (Resend-powered HTML digest). Tag `agents-v0.3.0`.
- **#3 Scheduler** ships `news-scheduler-dev` (3-op list Lambda) plus two Step Functions state machines: `news-cron-pipeline-dev` (daily fan-out triggered by EventBridge cron at 21:00 UTC) and `news-remix-user-dev` (single-user re-run). Tag `scheduler-v0.4.0`.

See [docs/superpowers/specs/](docs/superpowers/specs/) for design specs and [docs/superpowers/plans/](docs/superpowers/plans/) for implementation plans. Full sub-project breakdown (#0 through #6) is in [AGENTS.md](AGENTS.md).

Architecture diagrams: [docs/architecture.md](docs/architecture.md).

## What Foundation ships

- `packages/schemas/` — Pydantic v2 cross-package contracts (`Article`, `UserProfile`, `Digest`, `EmailSend`, `AuditLog`)
- `packages/config/` — env-backed settings + YAML loaders for `sources.yml` and `user_profile.yml`
- `packages/observability/` — loguru logging, OpenAI + Langfuse tracing hook, `AuditLogger`, tenacity retry presets, prompt-injection sanitizer, structured-output validator, size caps
- `packages/db/` — async SQLAlchemy 2 + Alembic migrations + one repository per aggregate, targeting Supabase Postgres
- `scripts/seed_user.py` + `scripts/reset_db.py` dev utilities
- 57 tests (unit + integration via `testcontainers-postgres`)
- GitHub Actions CI (ruff + mypy + pytest) and pre-commit hooks (ruff, mypy, detect-secrets)

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12 | Declared in `.python-version` |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | Workspace + dependency manager |
| Docker | any | Used by `testcontainers-postgres` for integration tests |
| Node.js | ≥ 20 | Only for the `rss-mcp` binary (used in sub-project #1) |
| A Supabase project | — | Postgres 16. Create at https://supabase.com |

## First-time setup

### 1. Clone and install

```sh
git clone git@github.com:PatrickCmd/ai-agents-news-aggregator.git
cd ai-agents-news-aggregator
make install-dev                  # uv sync + pre-commit install
```

### 2. Configure environment

```sh
cp .env.example .env
```

Fill in `.env` with real values. Minimum required for Foundation:

| Variable | Used by |
|---|---|
| `SUPABASE_DB_URL` | Alembic migrations (Session pooler, port 5432) |
| `SUPABASE_POOLER_URL` | Runtime queries (Transaction pooler, port 6543 — pgbouncer) |
| `OPENAI_API_KEY` | Web-search agent in sub-project #1 onwards |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Optional; tracing no-ops if unset |
| `LOG_LEVEL` | Defaults to `INFO` |
| `ENV` | `dev` / `staging` / `prod` |

Both DB URLs use the SQLAlchemy-async scheme:

```
postgresql+asyncpg://<user>:<pwd>@<host>:<port>/<db>
```

**Supabase connection strings (dashboard → Settings → Database → Connection string):**

- **Session pooler** (`aws-0-<region>.pooler.supabase.com:5432`) → put in `SUPABASE_DB_URL`. Username is `postgres.<project-ref>` (the tenant suffix is mandatory).
- **Transaction pooler** (`aws-0-<region>.pooler.supabase.com:6543`) → put in `SUPABASE_POOLER_URL`.
- **Direct** (`db.<project>.supabase.co:5432`) — skip it. Newer Supabase projects are **IPv6-only** on this host, which fails DNS resolution on most residential/corp networks (`socket.gaierror: [Errno 8]`). Use the Session pooler instead.

Replace `postgresql://` with `postgresql+asyncpg://` after copying from the dashboard.

### 3. Run database migrations

```sh
make migrate                      # alembic upgrade head
```

This creates five tables (`articles`, `users`, `digests`, `email_sends`, `audit_logs`) plus indexes, CHECK constraints, and `set_updated_at` triggers. The migration reads `SUPABASE_DB_URL` from `.env`.

Verify:

```sh
make migration-current            # shows the current revision on the DB
```

### 4. (Optional) Seed a dev user

Uses placeholder `clerk_user_id='dev-seed-user'` until Clerk lands in sub-project #4.

```sh
make seed                         # uv run python scripts/seed_user.py
```

Override the email via `SEED_USER_EMAIL=you@example.com make seed`.

### 5. Run tests

```sh
make test                         # all (Docker required for integration)
make test-unit                    # no Docker needed
make test-integration             # Docker required
```

## Running the scraper

Requirements beyond the foundation prerequisites:

- Node 20+ (needed by the rss-mcp binary and `@playwright/mcp@latest`)
- `npx` on PATH
- For transcripts: optional Webshare proxy credentials in `.env`

### Serve the API locally

```sh
make scraper-serve
# browse http://localhost:8000/docs
```

### Trigger an ingestion run

```sh
curl -X POST http://localhost:8000/ingest -H 'content-type: application/json' \
  -d '{"lookback_hours":6}'
```

Or via CLI (blocks until done, exit code reflects status):

```sh
make scraper-ingest
# or granular:
uv run python -m news_scraper ingest-rss --lookback-hours 6
uv run python -m news_scraper runs --limit 5
```

### Build and deploy

```sh
# First time only — IAM + state backend + terraform init
ADMIN_PROFILE=patrickcmd ./infra/setup-iam.sh              # IAM groups + aiengineer
make tf-bootstrap                                           # S3 state bucket
make tf-scraper-init STATE_BUCKET=news-aggregator-tf-state-<account>
cd infra/scraper && terraform workspace new dev && cd ../..
make tf-scraper-apply                                       # provision AWS infra
make secrets-sync ENV=dev                                   # push .env to SSM

# Iterate
make scraper-build                   # local docker build
make scraper-deploy-build            # build + push to ECR
make scraper-deploy                  # end-to-end: build + push + terraform apply + smoke test
```

The scraper exposes an ECS-auto-provisioned HTTPS endpoint. Grab it from
`terraform output scraper_endpoint` in `infra/scraper/`. Callers (#3 scheduler,
#4 API) are AWS-internal and reach it without public DNS.

See [infra/README.md](infra/README.md) for Terraform conventions.
See [docs/ecs-express-bootstrap.md](docs/ecs-express-bootstrap.md) for the
(minimal) manual prerequisites.

## Running the agents (#2)

Three independent Lambdas — digest (per-article LLM summary), editor
(per-user top-10 ranking), email (Resend-powered HTML digest). Each ships
as a zip artifact in S3 and lives in its own Terraform module.

```sh
# Local CLI (no AWS — talks to DB directly)
make agents-digest ARTICLE_ID=42
make agents-editor USER_ID=<uuid> LOOKBACK=24
make agents-email DIGEST_ID=17

# Deploy
make digest-deploy
make editor-deploy
MAIL_FROM=hi@yourdomain.com make email-deploy

# Live invoke + logs
make digest-invoke ARTICLE_ID=42
make agents-logs AGENT=email SINCE=10m
```

Sub-project #2 adds `RESEND_API_KEY` and `MAIL_FROM` to the SSM secrets tree
(`/news-aggregator/<env>/*`). See [infra/README.md](infra/README.md)
§ "Sub-project #2 — agents" for full lifecycle, IAM scope, and rollback.

## Running the scheduler (#3)

The cron pipeline state machine wires #1 → #2 into a daily end-to-end run
triggered by EventBridge `cron(0 21 * * ? *)` (00:00 EAT). A separate
remix-user state machine runs a single-user editor → email cycle on demand.

```sh
# Deploy the scheduler Lambda + state machines + EventBridge cron
make scheduler-deploy

# Run the full pipeline now (don't wait for the cron)
make cron-invoke
make cron-history                              # 5 most recent runs
make cron-describe NAME=<exec-name>            # full state-by-state trace

# Run remix for one user
make remix-invoke USER_ID=<uuid> LOOKBACK=24

# Local CLI (no AWS) — handy for debugging the 3 list ops
make scheduler-list-unsummarised LOOKBACK=24
make scheduler-list-active-users
make scheduler-list-new-digests

# Logs
make scheduler-logs SINCE=10m
make scheduler-logs-follow
```

Sub-project #3 extends the IAM groups with `AWSStepFunctionsFullAccess` and
`CloudWatchFullAccess` — re-run `./infra/setup-iam.sh` if you bootstrapped
before April 2026. See [infra/README.md](infra/README.md) § "Sub-project
#3 — scheduler" for failure modes and rollback recipe.

## Day-to-day commands

Everything is in the [Makefile](Makefile). `make help` prints them all.

| Task | Command |
|---|---|
| Sync dependencies | `make install` |
| Format code | `make fmt` |
| Lint + format check | `make lint` |
| Type-check | `make typecheck` |
| Full CI-equivalent check | `make check` |
| Run all pre-commit hooks | `make pre-commit` |
| Apply new migrations | `make migrate` |
| Roll back one migration | `make migrate-down` |
| Create new migration | `make migrate-rev MSG="add foo column"` |
| Destructive reset (dev DB only) | `make reset-db` |
| Clean caches | `make clean` |

## Database workflow

New migrations go in `packages/db/src/news_db/alembic/versions/`. Autogenerate from model changes:

```sh
make migrate-rev MSG="add score column to articles"
# review the generated file carefully
make migrate                      # apply
make migrate-down                 # revert if needed
```

`make reset-db` is guarded: it refuses to run unless the DB name in the URL contains `dev` or `local`. Your production Supabase DB named `postgres` is safe from this command.

## Project conventions

See [AGENTS.md](AGENTS.md) for the full conventions list. Highlights:

- **No `supabase-py` at runtime** — SQLAlchemy is the only data-access layer.
- **No raw dicts across package boundaries** — use Pydantic models from `news_schemas`.
- **Every user-supplied prompt** must pass through `news_observability.sanitizer.sanitize_prompt_input()` before hitting an LLM.
- **Every LLM response** must be validated via `news_observability.validators.validate_structured_output()`.
- **Every agent decision** should log to `audit_logs` via `AuditLogger`.
- **Frontend never talks to Supabase directly** — everything goes through FastAPI (sub-project #4).
- **Conventional Commits** (`feat(db): …`, `fix(observability): …`).

## Contributing

1. Pick a sub-project (see `AGENTS.md §Sub-project decomposition`).
2. Read its spec in `docs/superpowers/specs/`.
3. Work against its plan in `docs/superpowers/plans/`.
4. `make check` must be green before any commit or PR.

## License

TBD.
