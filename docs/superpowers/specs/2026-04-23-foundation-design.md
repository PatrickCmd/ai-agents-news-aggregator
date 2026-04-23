# Foundation (Sub-project #0) — Design Spec

- **Date:** 2026-04-23
- **Status:** Approved for implementation planning
- **Owner:** Patrick Walukagga
- **Scope:** Monorepo skeleton, shared packages (db, schemas, config, observability), initial Supabase schema, dev/test workflow, CI, and agent-guidance docs. No services, no agents, no frontend.

---

## 1. Overview

AI News Aggregator is a multi-source pipeline that ingests YouTube, RSS, and web-search content, summarizes it per article, ranks the top 10 items per user using an editor agent keyed on a user profile, and sends a personalized daily digest email. The long-term system is a multi-tenant SaaS with a Next.js frontend, Clerk auth, FastAPI on AWS Lambda, a scraper on ECS Express Mode, and agent Lambdas orchestrated by EventBridge.

This spec covers **only Sub-project #0 (Foundation)**: the shared library code and database schema every later sub-project depends on. Foundation produces no deployable service; it produces packages and a migrated Supabase schema.

---

## 2. Sub-project decomposition

The full system is decomposed into seven independent sub-projects. Each has its own brainstorm → spec → plan → implement cycle.

| # | Sub-project | Rationale |
|---|---|---|
| **0** | **Foundation (this spec)** — Supabase schema, SQLAlchemy models, migrations, config, shared `observability` + guardrails utilities, repo layout, CLAUDE.md/AGENTS.md | Everything else depends on this |
| 1 | Ingestion pipeline (ECS service): YouTube RSS + blog RSS + Playwright web-search agent → `articles` table | Pure backend; no auth, no UI |
| 2 | Digest + Editor + Email agents (Lambda chain) | Isolated agent pipeline consuming #1 output |
| 3 | Scheduler + orchestration: EventBridge → ECS → Lambda chain, retries, observability | Wires #1 and #2 together |
| 4 | API + Auth: FastAPI on Lambda, Clerk JWT, per-user profiles, on-demand digest endpoint | Biggest auth design surface |
| 5 | Frontend: Next.js + Clerk sign-in + profile editor + digest viewer + on-demand trigger, deployed to S3 + CloudFront | Depends on #4 API contract |
| 6 | Terraform + CI/CD: mirrors [alex-multi-agent-saas](https://github.com/PatrickCmd/alex-multi-agent-saas/tree/week4-observability) layout | Pulls everything into reproducible infra |

---

## 3. Architecture

### 3.1 Target system (full end state)

```mermaid
flowchart TB
    subgraph EXT[External Sources]
        YT[YouTube RSS]
        RSS[RSS Feeds<br/>OpenAI · Anthropic · AWS · ...]
        WEB[Web Pages]
    end

    subgraph SCHED[AWS EventBridge]
        CRON[Daily cron<br/>00:00 UTC]
    end

    subgraph ECSBOX[AWS ECS Express Mode]
        SCRAPER[Scraper Service · FastAPI]
        YTP[YouTube Pipeline]
        RSSP[RSS Pipeline<br/>via rss-mcp]
        WSA[Web Search Agent<br/>Playwright MCP]
    end

    subgraph LAM[AWS Lambda]
        DIGEST[Digest Agent<br/>per-article summaries]
        EDITOR[Editor Agent<br/>rank top 10 per user]
        EMAILAG[Email Agent<br/>intro + Resend send]
        API[FastAPI · API Gateway<br/>Clerk JWT]
    end

    subgraph SUPA[Supabase · Postgres]
        ARTICLES[(articles)]
        USERS[(users)]
        DIGESTS[(digests)]
        EMAILS[(email_sends)]
        AUDIT[(audit_logs)]
    end

    subgraph CLIENTS[Clients]
        FE[Next.js Frontend<br/>Clerk Sign-in<br/>S3 + CloudFront]
        INBOX[User Inbox]
    end

    subgraph OBS[Observability]
        LF[Langfuse]
        OAI[OpenAI Traces]
        CW[CloudWatch Logs]
    end

    YT --> YTP
    RSS --> RSSP
    WEB --> WSA

    CRON --> SCRAPER
    SCRAPER --> YTP
    SCRAPER --> RSSP
    SCRAPER --> WSA
    YTP --> ARTICLES
    RSSP --> ARTICLES
    WSA --> ARTICLES

    SCRAPER -- handoff --> DIGEST
    DIGEST --> ARTICLES
    DIGEST -- handoff per user --> EDITOR
    EDITOR --> USERS
    EDITOR --> ARTICLES
    EDITOR --> DIGESTS
    EDITOR -- handoff --> EMAILAG
    EMAILAG --> DIGESTS
    EMAILAG --> EMAILS
    EMAILAG --> INBOX

    FE -- API Gateway + Clerk JWT --> API
    API --> USERS
    API --> DIGESTS
    API -- on-demand trigger --> DIGEST

    WSA -. trace .-> LF
    WSA -. trace .-> OAI
    DIGEST -. trace .-> LF
    DIGEST -. trace .-> OAI
    EDITOR -. trace .-> LF
    EDITOR -. trace .-> OAI
    EMAILAG -. trace .-> LF
    EMAILAG -. trace .-> OAI

    SCRAPER -. audit .-> AUDIT
    DIGEST -. audit .-> AUDIT
    EDITOR -. audit .-> AUDIT
    EMAILAG -. audit .-> AUDIT

    SCRAPER -. logs .-> CW
    DIGEST -. logs .-> CW
    EDITOR -. logs .-> CW
    EMAILAG -. logs .-> CW
    API -. logs .-> CW
```

### 3.2 Sub-project dependency graph

```mermaid
flowchart LR
    subgraph S0[#0 Foundation · THIS SPEC]
        PKG[packages/* · schemas · db · config · observability]
    end
    subgraph S1[#1 Ingestion]
        ECSX[services/scraper]
    end
    subgraph S2[#2 Agents]
        AG[services/agents · digest · editor · email]
    end
    subgraph S3[#3 Orchestration]
        SCHX[EventBridge · handoff wiring]
    end
    subgraph S4[#4 API + Auth]
        APX[services/api + Clerk]
    end
    subgraph S5[#5 Frontend]
        WEBX[web/ Next.js]
    end
    subgraph S6[#6 Infra]
        IAC[Terraform + CI/CD]
    end
    S0 --> S1 --> S2 --> S3
    S0 --> S4 --> S5
    S1 --> S6
    S2 --> S6
    S3 --> S6
    S4 --> S6
    S5 --> S6
```

### 3.3 Architectural decisions (summary)

| Decision | Choice | Rationale |
|---|---|---|
| Tenancy | Hybrid — shared content tables (tenant-agnostic), per-user output tables | Articles are the same for all users; ranking is personal |
| Content modeling | Unified `articles` table with `source_type` discriminator + `raw jsonb` | One place for agents to query; one dedupe key |
| Data access | All SQLAlchemy 2.x async + Alembic; no supabase-py at runtime | One abstraction; typed queries; Alembic is battle-tested |
| Frontend data path | Next.js → API Gateway → FastAPI → SQLAlchemy (never directly to Supabase) | Simpler auth; no RLS needed |
| User profile storage | `users.profile` JSONB validated by Pydantic, matching `user_profile.yml` 1:1 | Read/written as a unit |
| Rankings | Not a separate table; stored as snapshot inside `digests.ranked_articles` JSONB | UI replays digest exactly as emailed |
| Repo layout | `uv` workspace monorepo | Matches alex-multi-agent-saas; tight Lambda bundles; strong package boundaries |
| Local dev DB | Remote Supabase only; no docker-compose | Simplicity; per-service Dockerfiles ship later with services |
| Tracing | OpenAI Agents SDK traces + Langfuse trace processor + `audit_logs` table | Three tiers: vendor dashboard, LLM-level spans, domain-level decisions |
| Typechecker | `mypy` | User preference |
| CI | GitHub Actions (lint + typecheck + tests) in Foundation | User chose to lockstep from the start |

---

## 4. Repo layout

```
ai-agent-news-aggregator/
├── pyproject.toml                       # uv workspace root
├── uv.lock
├── .env.example
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── ruff.toml
├── mypy.ini
├── CLAUDE.md                            # Claude Code guidance
├── AGENTS.md                            # portable agent guidance
├── packages/
│   ├── db/
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   └── src/news_db/
│   │       ├── __init__.py
│   │       ├── engine.py                # async engine + session factory
│   │       ├── models/                  # SQLAlchemy declarative models (one per file)
│   │       │   ├── __init__.py
│   │       │   ├── base.py              # DeclarativeBase + common mixins
│   │       │   ├── article.py
│   │       │   ├── user.py
│   │       │   ├── digest.py
│   │       │   ├── email_send.py
│   │       │   └── audit_log.py
│   │       ├── repositories/
│   │       │   ├── __init__.py
│   │       │   ├── article_repo.py
│   │       │   ├── user_repo.py
│   │       │   ├── digest_repo.py
│   │       │   ├── email_send_repo.py
│   │       │   └── audit_log_repo.py
│   │       ├── alembic/
│   │       │   ├── env.py
│   │       │   ├── script.py.mako
│   │       │   └── versions/
│   │       │       └── 0001_initial_schema.py
│   │       └── tests/                   # unit tests only
│   ├── schemas/
│   │   ├── pyproject.toml
│   │   └── src/news_schemas/
│   │       ├── __init__.py
│   │       ├── article.py               # SourceType enum, ArticleIn, ArticleOut
│   │       ├── user_profile.py          # UserProfile (JSONB), UserIn, UserOut
│   │       ├── digest.py                # RankedArticle, DigestStatus, DigestIn, DigestOut
│   │       ├── email_send.py            # EmailSendStatus, EmailSendIn, EmailSendOut
│   │       ├── audit.py                 # AgentName, DecisionType, AuditLogIn
│   │       └── tests/
│   ├── config/
│   │   ├── pyproject.toml
│   │   └── src/news_config/
│   │       ├── __init__.py
│   │       ├── loader.py                # YAML loader (migrated)
│   │       ├── settings.py              # env-backed Settings classes
│   │       ├── sources.yml              # migrated
│   │       ├── user_profile.yml         # migrated — used as seed
│   │       └── tests/
│   └── observability/
│       ├── pyproject.toml
│       └── src/news_observability/
│           ├── __init__.py
│           ├── logging.py               # loguru (migrated) + JSON mode for CloudWatch
│           ├── tracing.py               # configure_tracing(): OpenAI SDK + Langfuse processor
│           ├── audit.py                 # AuditLogger (writes audit_logs)
│           ├── retry.py                 # tenacity presets
│           ├── sanitizer.py             # prompt-injection patterns
│           ├── limits.py                # size caps + truncate_for_audit
│           ├── validators.py            # validate_structured_output wrapper
│           └── tests/
├── services/                            # stubs (filled in by later sub-projects)
│   ├── scraper/.gitkeep
│   ├── agents/.gitkeep
│   └── api/.gitkeep
├── infra/.gitkeep                       # sub-project #6
├── web/.gitkeep                         # sub-project #5
├── scripts/
│   ├── reset_db.py                      # drops public schema, re-runs migrations, re-seeds
│   └── seed_user.py                     # promotes user_profile.yml → users row
├── tests/
│   └── integration/                     # testcontainers-postgres
│       ├── conftest.py
│       ├── test_article_repo.py
│       ├── test_user_repo.py
│       ├── test_digest_repo.py
│       ├── test_email_send_repo.py
│       ├── test_audit_log_repo.py
│       └── test_alembic_migrations.py
└── docs/
    ├── architecture.md                  # mermaid diagrams of full system
    └── superpowers/specs/
        └── 2026-04-23-foundation-design.md
```

### 4.1 Code migration from current repo

| Current path | New path |
|---|---|
| `config/settings.py` | `packages/config/src/news_config/settings.py` |
| `config/loader.py` | `packages/config/src/news_config/loader.py` |
| `config/sources.yml` | `packages/config/src/news_config/sources.yml` |
| `config/user_profile.yml` | `packages/config/src/news_config/user_profile.yml` |
| `utils/logging.py` | `packages/observability/src/news_observability/logging.py` |
| `models/youtube.py` | `services/scraper/...` (deferred to #1) — YouTube-specific Pydantic models (`TranscriptSegment`, `VideoTranscript`, `ChannelVideo`, `ChannelInfo`) are scraper internals. Foundation only defines the generic cross-package contract `ArticleIn` / `ArticleOut` in `news_schemas.article` |
| `scrapers/base.py` | `services/scraper/...` (deferred to #1; stub placeholder for now) |
| `youtube_rss_pipeline/` | `services/scraper/...` (#1) |
| `rss_parser_pipeline/rss_parser_agent.py` | `services/scraper/...` (#1) |
| `rss_parser_pipeline/rss_pipeline.py` | `services/scraper/...` (#1) |
| `rss_parser_pipeline/schema.sql` | **replaced** by `packages/db/.../alembic/versions/0001_initial_schema.py` |
| `main.py` | **deleted** |
| `rss-mcp/` | stays at root; used by #1 |

**Note:** the existing Supabase `rss_items` table (if populated) will be dropped during `scripts/reset_db.py`. The user has confirmed no data preservation is required.

---

## 5. Data model

All timestamps are `timestamptz`. Per-user table IDs are `uuid` (matches Clerk's string subject cleanly); content table IDs are `bigserial`.

### 5.1 `articles` (tenant-agnostic, shared)

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `source_type` | text NOT NULL | CHECK IN `('rss','youtube','web_search')` |
| `source_name` | text NOT NULL | e.g. `openai_news`, `Anthropic`, channel name |
| `external_id` | text NOT NULL | RSS guid, YouTube video_id, or SHA256(url) for web_search |
| `title` | text NOT NULL | |
| `url` | text NOT NULL | |
| `author` | text | |
| `published_at` | timestamptz | |
| `content_text` | text | transcript / description / scraped body |
| `summary` | text | filled later by Digest Agent; Foundation leaves NULL |
| `tags` | text[] default `'{}'` | |
| `raw` | jsonb | source-specific extras (transcript segments, categories, thumbnail_url, channel_id) |
| `fetched_at` | timestamptz NOT NULL default now() | |
| `created_at` | timestamptz NOT NULL default now() | |
| `updated_at` | timestamptz NOT NULL default now() | auto-updated via trigger |

**Constraints & indexes:**
- `UNIQUE(source_type, external_id)` — cross-source dedup
- Index `(source_type, published_at DESC)`
- Index `(published_at DESC)`

### 5.2 `users`

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK default `gen_random_uuid()` | |
| `clerk_user_id` | text UNIQUE NOT NULL | Clerk `sub` claim; Foundation seed uses `'dev-seed-user'` |
| `email` | text UNIQUE NOT NULL | |
| `name` | text NOT NULL | |
| `email_name` | text NOT NULL | greeting name |
| `profile` | jsonb NOT NULL default `'{}'` | validated by `UserProfile` Pydantic model |
| `profile_completed_at` | timestamptz | NULL = incomplete; frontend redirects to profile form |
| `created_at` | timestamptz NOT NULL default now() | |
| `updated_at` | timestamptz NOT NULL default now() | auto-updated |

**Indexes:** `(clerk_user_id)`, `(email)`.

### 5.3 `digests` (per-user; includes ranked snapshot)

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `user_id` | uuid FK → `users.id` ON DELETE CASCADE | |
| `period_start` | timestamptz NOT NULL | article window start |
| `period_end` | timestamptz NOT NULL | article window end |
| `intro` | text | email agent's personalized intro |
| `ranked_articles` | jsonb NOT NULL | max 10 items: `{article_id, score, title, url, summary, why_ranked}` |
| `top_themes` | text[] default `'{}'` | |
| `article_count` | int NOT NULL | total articles considered (pre-ranking) |
| `status` | text NOT NULL default `'pending'` | CHECK IN `('pending','generated','emailed','failed')` |
| `error_message` | text | |
| `generated_at` | timestamptz NOT NULL default now() | |

**Indexes:** `(user_id, generated_at DESC)`, `(status)`.

### 5.4 `email_sends`

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `user_id` | uuid FK → `users.id` ON DELETE CASCADE | |
| `digest_id` | bigint FK → `digests.id` ON DELETE CASCADE | |
| `provider` | text NOT NULL default `'resend'` | |
| `to_address` | text NOT NULL | |
| `subject` | text NOT NULL | |
| `status` | text NOT NULL default `'pending'` | CHECK IN `('pending','sent','failed','bounced')` |
| `provider_message_id` | text | Resend message ID |
| `sent_at` | timestamptz | |
| `error_message` | text | |

**Indexes:** `(user_id, sent_at DESC)`, `(digest_id)`.

### 5.5 `audit_logs` (AI decision log)

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `timestamp` | timestamptz NOT NULL default now() | |
| `agent_name` | text NOT NULL | `'digest_agent'` / `'editor_agent'` / `'email_agent'` / `'web_search_agent'` |
| `user_id` | uuid FK → `users.id` ON DELETE SET NULL | NULL for ingestion agents |
| `decision_type` | text NOT NULL | `'summary'` / `'rank'` / `'intro'` / `'search_result'` |
| `input_summary` | text | size-capped |
| `output_summary` | text | size-capped |
| `metadata` | jsonb | token counts, model name, latency_ms, tool calls |

**Indexes:** `(agent_name, timestamp DESC)`, partial `(user_id, timestamp DESC) WHERE user_id IS NOT NULL`.

### 5.6 Auto-update triggers

A single `set_updated_at()` trigger function is defined once and attached to `articles.updated_at` and `users.updated_at`.

---

## 6. Shared packages

### 6.1 `packages/schemas/` (Pydantic v2)

Every package boundary speaks Pydantic; no raw dicts cross packages.

- `article.py` — `SourceType` enum (`rss`/`youtube`/`web_search`), `ArticleIn`, `ArticleOut`
- `user_profile.py` — `UserProfile` (validates JSONB blob; mirrors `user_profile.yml`), `UserIn`, `UserOut`, sub-models `Interests`, `Preferences`, `ReadingTime`
- `digest.py` — `RankedArticle`, `DigestStatus` enum, `DigestIn`, `DigestOut`
- `email_send.py` — `EmailSendStatus` enum, `EmailSendIn`, `EmailSendOut`
- `audit.py` — `AgentName` enum, `DecisionType` enum, `AuditLogIn`

### 6.2 `packages/config/`

- `settings.py` — one class per concern:
  - `DatabaseSettings` (`supabase_db_url`, `supabase_pooler_url`)
  - `OpenAISettings` (existing)
  - `YouTubeProxySettings` (existing)
  - `LangfuseSettings` (`public_key`, `secret_key`, `host`)
  - `ResendSettings` (`api_key`)
  - `AppSettings` (`env: Literal['dev','staging','prod']`, `log_level`)
- `loader.py` — YAML loader pointed at `sources.yml` and `user_profile.yml` inside the package
- `sources.yml`, `user_profile.yml` — migrated files

### 6.3 `packages/observability/`

- `logging.py` — loguru setup + optional `setup_json_logging()` mode for Lambda/ECS CloudWatch
- `tracing.py` — `configure_tracing(enable_langfuse: bool = True)` — idempotent; sets up OpenAI Agents SDK tracing and adds Langfuse as a trace processor when keys are configured
- `audit.py` — `AuditLogger` class with `async log_decision(AuditLogIn)`; writes via `AuditLogRepository`; fire-and-forget (errors logged but never raised)
- `retry.py` — preset tenacity decorators: `@retry_transient` (network/5xx), `@retry_llm` (rate-limit-aware exponential backoff)
- `sanitizer.py` — `sanitize_prompt_input(text) -> str` strips known prompt-injection patterns; raises `PromptInjectionError` on hard-block matches
- `limits.py` — constants `MAX_AUDIT_INPUT_CHARS`, `MAX_AUDIT_OUTPUT_CHARS`, `MAX_LLM_RESPONSE_CHARS` and helper `truncate_for_audit(s, limit) -> str`
- `validators.py` — `validate_structured_output(model: type[BaseModel], raw) -> BaseModel`; catches `ValidationError`, logs to audit, raises typed `StructuredOutputError` for retry decisions

### 6.4 `packages/db/`

**Engine + session:**
```python
# news_db/engine.py — shape only
async def get_engine() -> AsyncEngine: ...                  # singleton per process
@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]: ...
```

- Runtime uses `SUPABASE_POOLER_URL` with asyncpg `statement_cache_size=0` (pgbouncer transaction mode)
- Alembic `env.py` uses `SUPABASE_DB_URL` (direct port 5432) — migrations can't go through transaction-mode pgbouncer

**Repositories** — one per aggregate, async, constructor takes `AsyncSession`, methods return Pydantic `*Out` models:

- `ArticleRepository` — `upsert_many(list[ArticleIn]) -> int`, `get_recent(hours, source_types=None) -> list[ArticleOut]`, `get_by_id(id) -> ArticleOut | None`
- `UserRepository` — `upsert_by_clerk_id(UserIn) -> UserOut`, `get_by_clerk_id(str) -> UserOut | None`, `get_by_id(uuid) -> UserOut | None`, `mark_profile_complete(user_id) -> UserOut`, `update_profile(user_id, UserProfile) -> UserOut`
- `DigestRepository` — `create(DigestIn) -> DigestOut`, `update_status(id, status, error=None) -> DigestOut`, `get_recent_for_user(user_id, limit) -> list[DigestOut]`, `get_by_id(id) -> DigestOut | None`
- `EmailSendRepository` — `create(EmailSendIn) -> EmailSendOut`, `mark_sent(id, provider_message_id) -> EmailSendOut`, `mark_failed(id, error) -> EmailSendOut`
- `AuditLogRepository` — `insert(AuditLogIn) -> None`

---

## 7. SQLAlchemy + Alembic

- SQLAlchemy 2.x async (`AsyncEngine`, `AsyncSession`) with the `asyncpg` driver
- Declarative models using `DeclarativeBase`; one model class per file; `TimestampMixin` provides `created_at`/`updated_at`
- Alembic with async `env.py`; one initial revision `0001_initial_schema.py` creating all five tables, CHECK constraints, UNIQUE constraints, indexes, and the `set_updated_at()` trigger
- Model files import `Base` from `models/base.py`; `models/__init__.py` re-exports all models so Alembic autogenerate can discover them

---

## 8. Dev + testing workflow

### 8.1 Setup
```
uv sync                                                    # install workspace
cp .env.example .env                                       # fill in Supabase + API keys
uv run alembic -c packages/db/alembic.ini upgrade head
uv run python scripts/seed_user.py
uv run pytest
```

### 8.2 Destructive reset (dev only)
```
uv run python scripts/reset_db.py --confirm
```
- Drops and recreates the `public` schema, re-runs migrations, re-seeds.
- **Foot-gun guard:** refuses to run unless the database name in the connection URL contains `dev` or `local`. This prevents accidental production wipes.

### 8.3 Testing strategy

- **Unit tests** (co-located under each package's `tests/` directory): schema validation corner cases, sanitizer patterns, retry decorators, size-cap truncation, tracing processor configuration.
- **Integration tests** (`tests/integration/`): `testcontainers-postgres` spawns an ephemeral Postgres 16 container per test session, runs Alembic migrations, each test runs inside a rolled-back transaction. No docker-compose involved — `testcontainers` uses the Docker socket directly.
- **Migration test**: `alembic upgrade head` followed by `alembic downgrade base` must leave no residual objects.
- **Coverage target**: 80% for `packages/db/repositories/` and `packages/observability/`. Schemas get implicit coverage via repo tests.

---

## 9. Environment variables

See `.env.example`:

```
SUPABASE_DB_URL=postgresql+asyncpg://postgres:pwd@db.xxx.supabase.co:5432/postgres_dev
SUPABASE_POOLER_URL=postgresql+asyncpg://postgres:pwd@aws-0-region.pooler.supabase.com:5432/postgres_dev
OPENAI_API_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
YOUTUBE_PROXY_ENABLED=false
YOUTUBE_PROXY_USERNAME=
YOUTUBE_PROXY_PASSWORD=
RESEND_API_KEY=
LOG_LEVEL=INFO
ENV=dev
```

---

## 10. CI (GitHub Actions)

`.github/workflows/ci.yml` runs on pull requests to `main`:

1. Checkout
2. Install `uv`
3. `uv sync`
4. `uv run ruff check`
5. `uv run ruff format --check`
6. `uv run mypy packages`
7. `uv run pytest` (integration tests require Docker; Actions runners have it by default)

### Pre-commit

`.pre-commit-config.yaml` with:
- `ruff` (lint + format)
- `mypy` (fast mode)
- `end-of-file-fixer`, `trailing-whitespace`
- `detect-secrets`

---

## 11. Non-goals and explicit constraints

Calling these out so they don't drift in later sub-projects:

- **No client-side Supabase access.** The Next.js frontend talks only to FastAPI via API Gateway. No RLS policies are required now or ever.
- **No separate `rankings` table.** Rankings live inside `digests.ranked_articles` JSONB.
- **No `sources` table.** Sources are configured in `packages/config/src/news_config/sources.yml`.
- **No supabase-py at runtime.** SQLAlchemy is the only data-access abstraction.
- **No docker-compose.** Local dev points at remote Supabase; tests use `testcontainers-postgres`; services ship their own Dockerfiles in sub-projects #1–#3.
- **No code changes to scrapers or agents in Foundation.** Existing scraper/pipeline files are moved to `services/scraper/` as stubs-in-place; the rewrite is sub-project #1.

---

## 12. Risks & known gotchas

| Risk | Mitigation |
|---|---|
| pgbouncer transaction mode breaks asyncpg prepared statements | `statement_cache_size=0` in the async engine URL; documented in `engine.py` docstring |
| Alembic migration against pgbouncer fails mysteriously | `alembic.ini` / `env.py` uses the DIRECT `SUPABASE_DB_URL`, not the pooler URL |
| Langfuse keys missing in dev → tracing errors | `configure_tracing()` no-ops the Langfuse processor when keys are unset; logs a warning |
| `reset_db.py` wipes prod | `--confirm` flag + hostname guard (`dev`/`local` in DB name) |
| Seed user has no Clerk ID in Foundation | Use placeholder `'dev-seed-user'`; sub-project #4 migrates or replaces seed row when Clerk lands |
| YAML profile and DB profile drift | `UserProfile` Pydantic model is the single source of truth; `seed_user.py` validates YAML against it before writing |
| Pooler DNS caching at Lambda cold-start | Documented as a known Lambda/Supabase issue; workaround belongs to sub-project #3 orchestration, not Foundation |

---

## 13. Reference patterns for later sub-projects

Not used in Foundation, but captured here so later sub-projects mirror them:

- **ECS service Dockerfile** (pattern for sub-project #1 scraper): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/researcher/Dockerfile
- **ECS deploy script** (pattern for sub-project #1 / #6): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/researcher/deploy.py
- **Lambda container packager** (pattern for sub-project #2 agents): https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/planner/package_docker.py, https://github.com/PatrickCmd/alex-multi-agent-saas/blob/week4-observability/backend/reporter/package_docker.py

---

## 14. Appendix — existing code inventory

For reference, the current repo has:

- `config/settings.py` — `OpenAISettings`, `YouTubeProxySettings` classes (keep; migrate + extend)
- `config/loader.py` — YAML `Config` class (keep; migrate)
- `config/sources.yml` — YouTube channel list, OpenAI/Anthropic flags (keep; migrate)
- `config/user_profile.yml` — single-user profile YAML (keep; drives the `UserProfile` schema)
- `utils/logging.py` — loguru setup (keep; migrate)
- `models/youtube.py` — Pydantic models for YouTube data (migrate; generalize into `ArticleIn` + YouTube-specific `raw` payload)
- `scrapers/base.py` — abstract base class (keep for #1)
- `youtube_rss_pipeline/youtube_rss.py` — working YouTube RSS + transcript scraper (keep for #1)
- `rss_parser_pipeline/rss_parser_agent.py` — rss-mcp agent using OpenAI Agents SDK (keep for #1)
- `rss_parser_pipeline/rss_pipeline.py` — async pipeline with supabase-py upsert (rewrite to SQLAlchemy for #1)
- `rss_parser_pipeline/schema.sql` — `rss_items` table (replace with Alembic `0001_initial_schema`)
- `rss-mcp/` — the RSS MCP server binary (keep; used by #1)
- `main.py` — empty placeholder (delete)
