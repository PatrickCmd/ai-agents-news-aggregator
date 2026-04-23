# AGENTS.md

Portable guidance for any coding agent (Claude Code, Cursor, Aider, OpenAI Codex, Windsurf, Copilot) working in this repo. Read this before editing code.

## What this project is

AI News Aggregator — a multi-source pipeline that ingests YouTube RSS, blog RSS feeds, and web-search content, summarizes each article with an LLM, ranks the top 10 items per user using an editor agent keyed on a user profile, and sends a personalized daily digest email. Long-term: multi-tenant SaaS with a Next.js frontend, Clerk auth, FastAPI on AWS Lambda, a scraper on ECS Express Mode, and agent Lambdas orchestrated by EventBridge.

## Sub-project decomposition

The system is broken into seven independent sub-projects. Each has its own brainstorm → spec → plan → implement cycle. Know which one you're in before making changes.

| # | Sub-project | Status |
|---|---|---|
| **0** | **Foundation** — monorepo skeleton, shared packages (`db`, `schemas`, `config`, `observability`), Supabase schema, dev/test workflow, CI | current |
| 1 | Ingestion pipeline (ECS service): RSS + YouTube + Playwright web-search | not started |
| 2 | Digest + Editor + Email agents (Lambda chain) | not started |
| 3 | Scheduler + orchestration (EventBridge → ECS → Lambda) | not started |
| 4 | API + Auth (FastAPI on Lambda, Clerk JWT) | not started |
| 5 | Frontend (Next.js + Clerk + S3/CloudFront) | not started |
| 6 | Infra (Terraform + CI/CD) | not started |

Design spec for the current sub-project lives at `docs/superpowers/specs/`. Read the relevant spec file before starting work.

## Repo layout

```
ai-agent-news-aggregator/
├── packages/                   # shared library code (no deployables)
│   ├── db/                     # SQLAlchemy models + Alembic migrations + repositories
│   ├── schemas/                # Pydantic v2 cross-package contracts
│   ├── config/                 # YAML loader, env-backed Settings, sources.yml, user_profile.yml
│   └── observability/          # loguru, tracing (OpenAI + Langfuse), audit, retry, sanitizer, limits, validators
├── services/                   # deployables — filled in by sub-projects #1-#4
│   ├── scraper/                # ECS Express — RSS + YouTube + web-search
│   ├── agents/                 # Lambda — digest, editor, email
│   └── api/                    # Lambda — FastAPI + Clerk
├── infra/                      # Terraform — sub-project #6
├── web/                        # Next.js frontend — sub-project #5
├── scripts/                    # dev utilities (reset_db.py, seed_user.py)
├── tests/integration/          # testcontainers-postgres integration tests
├── docs/
│   ├── architecture.md         # mermaid diagrams of the full system
│   └── superpowers/specs/      # design specs, one per sub-project
└── rss-mcp/                    # RSS MCP server binary (used by #1)
```

## Conventions

### Package boundaries
- Every cross-package contract is a **Pydantic v2 model** from `packages/schemas/`. **Never pass raw dicts across package boundaries.**
- `packages/db/` exports repository classes only. It does not export SQLAlchemy models; callers consume Pydantic `*Out` types.
- `packages/observability/` is the ONLY place that owns logging, tracing, audit, retry, input sanitization, and response-size caps. Services and agents import from it; they never roll their own.
- `packages/config/` is the only place that reads env vars or YAML files.

### Data access
- **SQLAlchemy 2.x async is the only runtime data-access layer.** No `supabase-py` for reads or writes. The frontend does not talk to Supabase directly — it goes through FastAPI.
- Runtime connections use `SUPABASE_POOLER_URL` (pgbouncer transaction mode) with asyncpg `statement_cache_size=0`. Migrations use the direct `SUPABASE_DB_URL`.
- All code is async. No sync SQLAlchemy sessions in application code.

### Schema and migrations
- Schema changes happen only via Alembic revisions under `packages/db/src/news_db/alembic/versions/`.
- Never hand-edit the database schema through Supabase's SQL editor. If you ran a manual change, convert it to a migration before committing.
- `scripts/reset_db.py --confirm` is dev-only. It refuses to run against DB names without `dev` or `local` in them. Do not relax this guard.

### Code style
- `ruff` for lint + format (config in `ruff.toml`).
- `mypy` for typechecking (config in `mypy.ini`).
- Strict typing: every function has full type annotations. No `Any` except at clearly documented boundaries.
- One SQLAlchemy model per file in `packages/db/src/news_db/models/`.
- Private helpers start with `_`.

### Error handling and observability
- **Every user-supplied prompt must pass through `observability.sanitizer.sanitize_prompt_input()` before reaching an LLM.**
- Every LLM response must be validated via `observability.validators.validate_structured_output()` against a Pydantic model.
- Every agent decision logs to `audit_logs` via `observability.audit.AuditLogger`. Audit writes are fire-and-forget (never raise into caller).
- Every transient I/O call uses tenacity presets from `observability.retry` (`@retry_transient` for network/5xx, `@retry_llm` for rate-limit-aware backoff).
- Never log `SUPABASE_DB_URL`, `OPENAI_API_KEY`, `CLERK_SECRET_KEY`, or any `_KEY` / `_SECRET` env var.

### Testing policy
- Every repository method needs at least one integration test.
- Every Pydantic schema needs at least one valid case and one invalid case.
- Unit tests are co-located: `packages/<name>/src/<name>/tests/`.
- Integration tests live in `tests/integration/`. They use `testcontainers-postgres` — Docker must be running.
- Don't mark a task complete while tests fail, mypy errors, or ruff errors exist. "Done" means `uv run pytest && uv run mypy packages && uv run ruff check` all pass.

### Commits and PRs
- Conventional Commits (`feat(db): …`, `fix(observability): …`, `chore(ci): …`, `docs: …`).
- One logical change per commit. No "WIP" commits on merged branches.
- PR descriptions reference the sub-project number: "Sub-project #0 — initial Alembic migration."
- Every PR runs the full CI pipeline (lint + typecheck + tests) before merge.

## How to run things

```sh
# install
uv sync

# env
cp .env.example .env && edit .env

# migrations
uv run alembic -c packages/db/alembic.ini upgrade head

# seed dev user
uv run python scripts/seed_user.py

# tests (Docker must be running — testcontainers)
uv run pytest

# lint + typecheck
uv run ruff check
uv run ruff format --check
uv run mypy packages

# destructive reset (dev only)
uv run python scripts/reset_db.py --confirm
```

## What NOT to do

Anti-patterns that will break invariants in this repo. Reject these on review:

- Do not use `docker-compose`. Local dev points at remote Supabase; tests use testcontainers; services (in #1–#3) ship their own Dockerfiles.
- Do not use `supabase-py` at runtime. SQLAlchemy is the only data-access abstraction.
- Do not create a `rankings` table. Rankings live inside `digests.ranked_articles` JSONB.
- Do not create a `sources` table. Sources live in `packages/config/src/news_config/sources.yml`.
- Do not add RLS policies. All reads go through FastAPI with application-layer user filtering.
- Do not write raw SQL in application code. Raw SQL belongs in Alembic migrations only.
- Do not pass raw dicts across package boundaries. Use Pydantic schemas.
- Do not skip `sanitize_prompt_input()` before LLM calls. Prompt injection is in-scope.
- Do not log secrets. Review every `logger.info` touching env vars.
- Do not commit `.env`. It's in `.gitignore` for a reason.
- Do not bypass `scripts/reset_db.py` guards.

## Security

- All secrets in `.env` (local) or AWS Secrets Manager (deployed). `.env` is gitignored.
- `pre-commit` runs `detect-secrets` — if it flags something, don't `--no-verify` your way past it.
- Prompt-injection sanitization is mandatory before any user-supplied text reaches an LLM.
- Audit logs size-cap input and output text via `observability.limits`.

## External references

Pattern references for future sub-projects (not used in Foundation):

- ECS service Dockerfile (for #1 scraper): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/researcher/Dockerfile
- ECS deploy script (for #1 / #6): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/researcher/deploy.py
- Lambda container packager (for #2 agents): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/planner/package_docker.py
