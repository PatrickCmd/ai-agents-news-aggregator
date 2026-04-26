# AGENTS.md

Portable guidance for any coding agent (Claude Code, Cursor, Aider, OpenAI Codex, Windsurf, Copilot) working in this repo. Read this before editing code.

## What this project is

AI News Aggregator — a multi-source pipeline that ingests YouTube RSS, blog RSS feeds, and web-search content, summarizes each article with an LLM, ranks the top 10 items per user using an editor agent keyed on a user profile, and sends a personalized daily digest email. Long-term: multi-tenant SaaS with a Next.js frontend, Clerk auth, FastAPI on AWS Lambda, a scraper on ECS Express Mode, and agent Lambdas orchestrated by EventBridge.

## Sub-project decomposition

The system is broken into seven independent sub-projects. Each has its own brainstorm → spec → plan → implement cycle. Know which one you're in before making changes.

| # | Sub-project | Status |
|---|---|---|
| **0** | Foundation — monorepo skeleton, shared packages (`db`, `schemas`, `config`, `observability`), Supabase schema, dev/test workflow, CI | shipped — tag `foundation-v0.1.1` |
| **1** | Ingestion pipeline (ECS Express service): RSS + YouTube + Playwright web-search, plus per-sub-project Terraform under `infra/scraper/` | shipped — tag `ingestion-v0.2.1` |
| **2** | Digest + Editor + Email agents (Lambda chain) — Lambda zips on S3, per-agent Terraform under `infra/{digest,editor,email}/` | shipped — tag `agents-v0.3.0` |
| 3 | Scheduler + orchestration (EventBridge → ECS → Lambda) | not started |
| 4 | API + Auth (FastAPI on Lambda, Clerk JWT) | not started |
| 5 | Frontend (Next.js + Clerk + S3/CloudFront) | not started |
| 6 | CI/CD pipelines + cross-sub-project ops (per-sub-project Terraform is owned by each sub-project, not #6) | not started |

Design spec for the current sub-project lives at `docs/superpowers/specs/`. Read the relevant spec file before starting work.

## Repo layout

```
ai-agent-news-aggregator/
├── packages/                       # shared library code (no deployables)
│   ├── db/                         # SQLAlchemy models + Alembic + repositories
│   ├── schemas/                    # Pydantic v2 cross-package contracts (incl. ScraperRunIn/Out)
│   ├── config/                     # YAML loader, env Settings, sources.yml, user_profile.yml
│   └── observability/              # logging, tracing, audit, retry, sanitizer, validators, costs
├── services/                       # deployables — one per sub-project that ships compute
│   ├── scraper/                    # ECS Express — RSS + YouTube + web-search (#1)
│   │   ├── Dockerfile
│   │   ├── deploy.py               # build → ECR push → terraform apply
│   │   └── src/news_scraper/
│   │       ├── api/                # FastAPI routes
│   │       ├── pipelines/          # per-source pipelines + adapters
│   │       ├── main.py             # uvicorn entry
│   │       └── cli.py              # Typer CLI
│   ├── agents/                     # Lambda — digest, editor, email (#2)
│   └── api/                        # Lambda — FastAPI + Clerk (#4)
├── infra/                          # per-sub-project Terraform modules + bootstrap
│   ├── README.md                   # apply order, recovery, day-to-day ops
│   ├── bootstrap/                  # one-time S3 + DynamoDB state backend
│   ├── scraper/                    # ECR, ECS Express, IAM, SSM, log group (#1)
│   │   ├── *.tf
│   │   ├── service.sh              # ECS service helper (pause/resume/pin/redeploy/status)
│   │   └── sync_secrets.py         # push .env into SSM SecureString
│   └── setup-iam.sh                # one-time NewsAggregator{Core,Compute}Access groups
├── web/                            # Next.js frontend (#5)
├── scripts/                        # dev utilities (reset_db.py, seed_user.py)
├── tests/integration/              # testcontainers-postgres integration tests
├── docs/
│   ├── architecture.md             # mermaid diagrams
│   └── superpowers/specs/          # design specs, one per sub-project
└── rss-mcp/                        # RSS MCP server binary (used by #1)
```

## Conventions

### Package boundaries
- Every cross-package contract is a **Pydantic v2 model** from `packages/schemas/`. **Never pass raw dicts across package boundaries.**
- `packages/db/` exports repository classes only. It does not export SQLAlchemy models; callers consume Pydantic `*Out` types.
- `packages/observability/` is the ONLY place that owns logging, tracing, audit, retry, input sanitization, response-size caps, and **LLM cost tracking** (`costs.py`). Services and agents import from it; they never roll their own.
- `packages/config/` is the only place that reads env vars or YAML files.

### Data access
- **SQLAlchemy 2.x async is the only runtime data-access layer.** No `supabase-py` for reads or writes. The frontend does not talk to Supabase directly — it goes through FastAPI.
- Supabase has three connection URLs in the dashboard. Use these mappings:
  - `SUPABASE_DB_URL` = **Session pooler** (`aws-0-<region>.pooler.supabase.com:5432`) — for migrations
  - `SUPABASE_POOLER_URL` = **Transaction pooler** (`aws-0-<region>.pooler.supabase.com:6543`, pgbouncer) — for runtime
  - Both use username `postgres.<project-ref>` (the tenant suffix is mandatory)
  - **Avoid `db.<project>.supabase.co`** — the direct host is IPv6-only on newer projects and fails DNS on most networks
- Runtime asyncpg uses `statement_cache_size=0` (pgbouncer transaction mode is incompatible with prepared statements).
- All code is async. No sync SQLAlchemy sessions in application code.

### Schema and migrations
- Schema changes happen only via Alembic revisions under `packages/db/src/news_db/alembic/versions/`.
- Never hand-edit the database schema through Supabase's SQL editor. If you ran a manual change, convert it to a migration before committing.
- `scripts/reset_db.py --confirm` is dev-only. It refuses to run against DB names without `dev` or `local` in them. Do not relax this guard.

### Infrastructure (per sub-project)
- Each deployable owns **its own Terraform root module** at `infra/<name>/` — independently applied.
- Shared remote state: `s3://news-aggregator-tf-state-<account>/...` with S3 native locking (`use_lockfile = true`). Created once by `infra/bootstrap/`.
- Per-env separation: Terraform workspaces (`dev`, `prod`), not duplicated directories.
- Per-module backend: same bucket, different `key=<name>/terraform.tfstate`.
- AWS auth via `AWS_PROFILE=aiengineer`. IAM perms granted by groups `NewsAggregatorCoreAccess` (scraper-era services) + `NewsAggregatorComputeAccess` (Lambda, API Gateway, EventBridge, S3, CloudFront), set up via `infra/setup-iam.sh`.
- Sub-project #6 owns CI/CD pipelines + cross-sub-project ops only — NOT a single mega-Terraform module.
- See `infra/README.md` for the full operational playbook (apply order, recovery, day-to-day ops).

### Models and pricing
- Default OpenAI model: **`gpt-5.4-mini`** (env: `OPENAI_MODEL`). Override per-agent only with reason.
- Pricing table is hardcoded in `news_observability.costs._PRICING`. Update it when OpenAI publishes new models or when pricing changes.
- Every LLM call must:
  1. Pass user-supplied prompt parts through `news_observability.sanitizer.sanitize_prompt_input`
  2. Validate the response with `news_observability.validators.validate_structured_output(SomeModel, raw)`
  3. Extract usage with `news_observability.costs.extract_usage(result, model=...)`
  4. Include `(model, input_tokens, output_tokens, total_tokens, requests, estimated_cost_usd, duration_ms)` in audit-log metadata
- For Pydantic models passed as `output_type=` to an OpenAI Agents SDK Agent: use plain `str` for URL fields, **never `HttpUrl`/`EmailStr`** — OpenAI structured outputs reject JSON Schema `format: "uri"` and similar URI-like formats. Validate URLs downstream when promoting to internal types.

### Code style
- `ruff` for lint + format (config in `ruff.toml`).
- `mypy` for typechecking (config in `mypy.ini`).
- Strict typing: every function has full type annotations. No `Any` except at clearly documented boundaries.
- One SQLAlchemy model per file in `packages/db/src/news_db/models/`.
- Private helpers start with `_`.

### Error handling and observability
- **Every user-supplied prompt must pass through `observability.sanitizer.sanitize_prompt_input()` before reaching an LLM.**
- Every LLM response must be validated via `observability.validators.validate_structured_output()` against a Pydantic model.
- Every agent decision logs to `audit_logs` via `observability.audit.AuditLogger`. Audit writes are fire-and-forget (never raise into caller). Include LLM usage from `costs.extract_usage` in the metadata.
- Every transient I/O call uses tenacity presets from `observability.retry` (`@retry_transient` for network/5xx, `@retry_llm` for rate-limit-aware backoff).
- Never log `SUPABASE_DB_URL`, `OPENAI_API_KEY`, `CLERK_SECRET_KEY`, or any `_KEY` / `_SECRET` env var.

### Testing policy
- Every repository method needs at least one integration test.
- Every Pydantic schema needs at least one valid case and one invalid case.
- Unit tests are co-located: `packages/<name>/src/<name>/tests/` and `services/<name>/src/<name>/tests/unit/`.
- Integration tests live in `tests/integration/`. They use `testcontainers-postgres` — Docker must be running.
- **Live tests** (`@pytest.mark.live`): for tests that hit real external services (rss-mcp, YouTube RSS, Playwright, real LLM calls). Deselected by default in CI. Run locally with `make test-scraper-live`.
- **FastAPI integration tests** must use `httpx.AsyncClient + ASGITransport`, NOT `fastapi.testclient.TestClient` (which spawns a thread-local event loop and fights pytest-asyncio + asyncpg).
- Don't mark a task complete while tests fail, mypy errors, or ruff errors exist. "Done" means `uv run pytest && uv run mypy packages services/<name>/src && uv run ruff check` all pass.

### Commits and PRs
- Conventional Commits (`feat(db): …`, `fix(observability): …`, `chore(ci): …`, `docs: …`).
- One logical change per commit. No "WIP" commits on merged branches.
- PR descriptions reference the sub-project number: "Sub-project #2 — initial digest agent."
- Every PR runs the full CI pipeline (lint + typecheck + tests) before merge.

## How to run things

### Foundation / repo-wide

```sh
# install
uv sync --all-packages

# env
cp .env.example .env && edit .env

# migrations
make migrate

# seed dev user
make seed

# tests (Docker must be running — testcontainers)
make check                          # ruff + mypy + pytest

# lint + typecheck individually
uv run ruff check
uv run ruff format --check
uv run mypy packages services/scraper/src

# destructive reset (dev only)
make reset-db
```

### Sub-project #1 (Ingestion) — operational commands

The scraper service is live in AWS; these are how you operate it.

```sh
# Local
make scraper-serve              # FastAPI on localhost:8000
make scraper-ingest             # CLI ingest, all 3 pipelines

# AWS deploy lifecycle
make scraper-bootstrap          # fresh-start: ECR + cluster + IAM + SSM + logs
make secrets-sync ENV=dev       # push .env into SSM SecureString
make scraper-deploy             # build + push image + apply terraform + smoke /healthz
make scraper-redeploy           # roll the running task with the latest :latest

# Live testing (suspends autoscaling so the task stays warm)
make scraper-pin-up             # 1 task, autoscaling suspended
make scraper-test-health
make scraper-test-ingest-rss LOOKBACK=6
make scraper-test-run RUN_ID=<uuid>
make scraper-logs SINCE=10m
make scraper-pin-down           # back to cost mode (autoscaling on, scale-to-0)

# Recovery
make scraper-recover            # fix "inconsistent result" tainted-state errors
make scraper-import-secrets     # fix ParameterAlreadyExists during apply
```

See `infra/README.md` for the full lifecycle, recovery scenarios, and AWS-side gotchas.

### Sub-project #2 (Agents) — operational commands

Three independent Lambda functions: `news-digest-dev`, `news-editor-dev`,
`news-email-dev`. Each is a zip artifact in S3, deployed via per-agent
Terraform modules under `infra/{digest,editor,email}/`.

```sh
# Local CLI (no AWS)
make agents-digest ARTICLE_ID=42                  # summarise one article
make agents-digest-sweep LOOKBACK=24              # sweep all unsummarised
make agents-editor USER_ID=<uuid> LOOKBACK=24     # rank for user
make agents-email DIGEST_ID=17                    # send via Resend
make agents-preview DIGEST_ID=17                  # render HTML to stdout (no send)

# AWS deploy lifecycle
make digest-deploy                                # build + S3 upload + terraform apply
make editor-deploy
MAIL_FROM=hi@yourdomain.com make email-deploy     # MAIL_FROM required (Resend-verified)

# Live invoke
make digest-invoke ARTICLE_ID=42
make editor-invoke USER_ID=<uuid>
make email-invoke DIGEST_ID=17

# Logs
make agents-logs AGENT=digest SINCE=10m
make agents-logs-follow AGENT=email
```

Lambdas read SSM SecureStrings at cold-start via
`news_config.lambda_settings.load_settings_from_ssm` — same SSM tree as #1
(`/news-aggregator/<env>/*`). The bootstrap module's `lambda_artifacts` S3
bucket holds the zips; each per-agent Terraform module reads the bucket
name inline (no `terraform_remote_state` indirection).

See `infra/README.md` § "Sub-project #2 — agents" for full lifecycle,
rollback, and IAM scope details.

## What NOT to do

Anti-patterns that will break invariants in this repo. Reject these on review:

- Do not use `docker-compose`. Local dev points at remote Supabase; tests use testcontainers; services ship their own Dockerfiles.
- Do not use `supabase-py` at runtime. SQLAlchemy is the only data-access abstraction.
- Do not point `SUPABASE_DB_URL` at the direct host (`db.<project>.supabase.co`) — it's IPv6-only on newer projects. Use the Session pooler.
- Do not create a `rankings` table. Rankings live inside `digests.ranked_articles` JSONB.
- Do not create a `sources` table. Sources live in `packages/config/src/news_config/sources.yml`.
- Do not add RLS policies. All reads go through FastAPI with application-layer user filtering.
- Do not write raw SQL in application code. Raw SQL belongs in Alembic migrations only.
- Do not pass raw dicts across package boundaries. Use Pydantic schemas.
- Do not skip `sanitize_prompt_input()` before LLM calls. Prompt injection is in-scope.
- Do not skip `extract_usage()` after an OpenAI Agents SDK run. Cost tracking is mandatory in every agent's audit-log metadata.
- Do not use `HttpUrl`/`EmailStr` (or any Pydantic type that emits JSON Schema `format: ...`) as the **`output_type` of an OpenAI Agents SDK agent**. OpenAI rejects them. Use `str` and validate downstream.
- Do not build Docker images for Fargate without `--platform=linux/amd64` on Apple Silicon. Mismatched arch fails with `exec format error`.
- Do not use `fastapi.testclient.TestClient` for async integration tests. Use `httpx.AsyncClient + ASGITransport`.
- Do not log secrets. Review every `logger.info` touching env vars.
- Do not commit `.env`. It's in `.gitignore` for a reason.
- Do not bypass `scripts/reset_db.py` guards.
- Do not run `terraform apply -replace=...` on the ECS Express service unless you've waited ~1h for the previous INACTIVE record to clear, OR rename the service. AWS retains INACTIVE service names for ~1h.
- Do not name the Lambda handler module anything other than `lambda_handler.py` at the agent's package root. AWS Lambda's handler config requires `handler = "lambda_handler.handler"`, and unit tests for these handlers MUST `sys.modules.pop("lambda_handler", None)` before each `import lambda_handler` to avoid cross-agent collisions in pytest's shared interpreter.
- Do not wrap the Resend HTTP client with `@retry_transient` inside `news_email.pipeline`. The retry decorator must wrap at the call site (Lambda handler / CLI) — wrapping inside the pipeline would retry the 4xx error mappings (auth/validation/rate-limit) which are deterministic failures.
- Do not use `data.terraform_remote_state.bootstrap` in the per-agent Lambda Terraform modules. The bootstrap module uses local state (chicken-and-egg). Compute the artifacts bucket name inline: `"news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}"`.

## Security

- All secrets in `.env` (local), SSM Parameter Store SecureString (AWS runtime), or AWS Secrets Manager (rotated/cross-account). `.env` is gitignored.
- `pre-commit` runs `detect-secrets` — if it flags something, don't `--no-verify` your way past it.
- Prompt-injection sanitization is mandatory before any user-supplied text reaches an LLM.
- Audit logs size-cap input and output text via `observability.limits`.
- Every IAM permission addition needs reason in the commit message — over-permissioning is a review red flag.

## External references

Pattern references for future sub-projects:

- ECS Express Terraform pattern: `infra/scraper/` (sets the per-sub-project convention).
- Lambda container packager (for #2 agents): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/planner/package_docker.py
- Live operational playbook: [`infra/README.md`](./infra/README.md).
