# Sub-project #4 — API + Auth — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a FastAPI-on-Lambda API behind API Gateway HTTP API that exposes six endpoints (`/healthz`, `/me`, `/me/profile`, `/digests`, `/digests/{id}`, `/remix`), validates Clerk JWTs via a FastAPI dependency, lazy-upserts users on first call, and triggers the existing `news-remix-user-dev` Step Functions state machine for on-demand digest re-runs.

**Architecture:** Single Lambda zip on S3 (mirrors #2/#3); Mangum bridges API Gateway HTTP API → ASGI → FastAPI; JWKS prefetched lazily and cached at module level for the container's lifetime; PyJWT validates RS256 against Clerk's public keys; same `news_db.engine.reset_engine()` warm-start pattern from #3; per-sub-project Terraform under `infra/api/` with `terraform_remote_state` reading `infra/scheduler/`'s outputs for the remix ARN.

**Tech Stack:** FastAPI, Mangum, PyJWT (with `cryptography` for RS256), Pydantic v2, pydantic-settings, boto3 (Step Functions), uvicorn (local dev), API Gateway HTTP API (v2), AWS Lambda (zip on S3), Terraform.

---

## File structure (locked in before tasks)

### New (created)

```
services/api/
├── pyproject.toml
├── package_docker.py
├── deploy.py
├── lambda_handler.py
└── src/news_api/
    ├── __init__.py
    ├── __main__.py
    ├── app.py
    ├── settings.py
    ├── deps.py
    ├── cli.py
    ├── auth/
    │   ├── __init__.py
    │   ├── jwks.py
    │   └── verify.py
    ├── routes/
    │   ├── __init__.py
    │   ├── healthz.py
    │   ├── me.py
    │   ├── digests.py
    │   └── remix.py
    ├── clients/
    │   ├── __init__.py
    │   └── stepfunctions.py
    └── tests/
        ├── __init__.py
        ├── conftest.py
        ├── unit/
        │   ├── __init__.py
        │   ├── test_jwks.py
        │   ├── test_verify.py
        │   └── test_stepfunctions.py
        └── integration/
            ├── __init__.py
            ├── conftest.py
            ├── test_healthz.py
            ├── test_me.py
            ├── test_profile.py
            ├── test_digests.py
            ├── test_remix.py
            └── test_jwt_regression.py

infra/api/
├── backend.tf
├── data.tf
├── variables.tf
├── main.tf
├── apigateway.tf
├── outputs.tf
├── terraform.tfvars.example
└── .gitignore
```

### Modified

- `packages/schemas/src/news_schemas/user_profile.py` — `UserProfile.empty()` classmethod.
- `packages/schemas/src/news_schemas/digest.py` — `DigestSummaryOut` projection.
- `packages/schemas/src/news_schemas/audit.py` — `AgentName.API`, `DecisionType.PROFILE_UPDATE`, `DecisionType.REMIX_TRIGGERED`.
- `packages/db/src/news_db/repositories/digest_repo.py` — `get_for_user(user_id, limit, before)`.
- `pyproject.toml` (root) — register `services/api` workspace member + `news_api` source.
- `Makefile` — append `# ---------- api (#4) ----------` block.
- `infra/README.md` — append "Sub-project #4 — API + Auth" section.
- `AGENTS.md` — flip #4 status, add layout entry, new ops section, anti-patterns.
- `README.md` — refresh status table + add "Running the API (#4)" section.

---

## Phase 0 — Schema additions

### Task 0.1: `UserProfile.empty()` classmethod

**Files:**
- Modify: [packages/schemas/src/news_schemas/user_profile.py](packages/schemas/src/news_schemas/user_profile.py)
- Test: `packages/schemas/src/news_schemas/tests/test_user_profile.py` (existing — append)

- [ ] **Step 1: Write the failing test**

Append to `packages/schemas/src/news_schemas/tests/test_user_profile.py`:

```python
from news_schemas.user_profile import UserProfile


def test_user_profile_empty_returns_validatable_instance():
    profile = UserProfile.empty()

    # All list fields are empty.
    assert profile.background == []
    assert profile.interests.primary == []
    assert profile.interests.secondary == []
    assert profile.interests.specific_topics == []
    assert profile.preferences.content_type == []
    assert profile.preferences.avoid == []
    assert profile.goals == []

    # ReadingTime has benign defaults (string fields are required by the schema).
    assert profile.reading_time.daily_limit == "30 minutes"
    assert profile.reading_time.preferred_article_count == "10"


def test_user_profile_empty_round_trips_through_json():
    profile = UserProfile.empty()
    rebuilt = UserProfile.model_validate(profile.model_dump(mode="json"))
    assert rebuilt == profile
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest packages/schemas/src/news_schemas/tests/test_user_profile.py::test_user_profile_empty_returns_validatable_instance -v
```

Expected: FAIL with `AttributeError: type object 'UserProfile' has no attribute 'empty'`.

- [ ] **Step 3: Add the classmethod**

Edit `packages/schemas/src/news_schemas/user_profile.py`. Insert after the existing `UserProfile` class fields, before `class UserIn`:

```python
class UserProfile(BaseModel):
    """Mirrors config/user_profile.yml. Stored as users.profile JSONB."""

    model_config = ConfigDict(extra="forbid")

    background: list[str] = Field(default_factory=list)
    interests: Interests
    preferences: Preferences
    goals: list[str] = Field(default_factory=list)
    reading_time: ReadingTime

    @classmethod
    def empty(cls) -> "UserProfile":
        """Empty / not-yet-onboarded profile.

        Used by the API's lazy-upsert path before the user has visited the
        profile editor. The editor agent filters by `profile_completed_at IS
        NOT NULL`, so empty profiles are inert until the user completes
        onboarding.
        """
        return cls(
            background=[],
            interests=Interests(primary=[], secondary=[], specific_topics=[]),
            preferences=Preferences(content_type=[], avoid=[]),
            goals=[],
            reading_time=ReadingTime(
                daily_limit="30 minutes",
                preferred_article_count="10",
            ),
        )
```

- [ ] **Step 4: Run tests to verify both pass**

```sh
uv run pytest packages/schemas/src/news_schemas/tests/test_user_profile.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add packages/schemas/src/news_schemas/user_profile.py packages/schemas/src/news_schemas/tests/test_user_profile.py
git commit -m "feat(schemas): UserProfile.empty() for lazy-upsert path"
```

---

### Task 0.2: `DigestSummaryOut` projection schema

**Files:**
- Modify: [packages/schemas/src/news_schemas/digest.py](packages/schemas/src/news_schemas/digest.py)
- Test: `packages/schemas/src/news_schemas/tests/test_digest.py` (existing — append)

- [ ] **Step 1: Write the failing test**

Append to `packages/schemas/src/news_schemas/tests/test_digest.py`:

```python
from datetime import datetime, timezone
from uuid import uuid4

from news_schemas.digest import DigestSummaryOut, DigestStatus


def test_digest_summary_out_excludes_ranked_articles():
    payload = {
        "id": 17,
        "user_id": uuid4(),
        "period_start": datetime(2026, 4, 26, tzinfo=timezone.utc),
        "period_end": datetime(2026, 4, 27, tzinfo=timezone.utc),
        "intro": "Hi there",
        "top_themes": ["agents", "infra"],
        "article_count": 7,
        "status": DigestStatus.GENERATED,
        "generated_at": datetime(2026, 4, 27, 5, 0, tzinfo=timezone.utc),
    }
    summary = DigestSummaryOut.model_validate(payload)
    assert summary.id == 17
    assert summary.article_count == 7
    assert summary.intro == "Hi there"
    assert "ranked_articles" not in summary.model_dump()
    assert "error_message" not in summary.model_dump()


def test_digest_summary_out_intro_optional():
    summary = DigestSummaryOut.model_validate({
        "id": 18,
        "user_id": uuid4(),
        "period_start": datetime(2026, 4, 26, tzinfo=timezone.utc),
        "period_end": datetime(2026, 4, 27, tzinfo=timezone.utc),
        "intro": None,
        "top_themes": [],
        "article_count": 0,
        "status": DigestStatus.PENDING,
        "generated_at": datetime(2026, 4, 27, 5, 0, tzinfo=timezone.utc),
    })
    assert summary.intro is None
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest packages/schemas/src/news_schemas/tests/test_digest.py::test_digest_summary_out_excludes_ranked_articles -v
```

Expected: FAIL with `ImportError: cannot import name 'DigestSummaryOut'`.

- [ ] **Step 3: Add the projection schema**

Edit `packages/schemas/src/news_schemas/digest.py`. Append at the end of the file:

```python
class DigestSummaryOut(BaseModel):
    """Lighter projection of `Digest` for list views.

    Excludes the heavy `ranked_articles` JSONB and `error_message`. Detail
    view (`GET /v1/digests/{id}`) returns full `DigestOut`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: UUID
    period_start: datetime
    period_end: datetime
    intro: str | None
    top_themes: list[str]
    article_count: int
    status: DigestStatus
    generated_at: datetime
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest packages/schemas/src/news_schemas/tests/test_digest.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add packages/schemas/src/news_schemas/digest.py packages/schemas/src/news_schemas/tests/test_digest.py
git commit -m "feat(schemas): DigestSummaryOut projection (excludes ranked_articles)"
```

---

### Task 0.3: `AgentName.API` + 2 new `DecisionType` values

**Files:**
- Modify: [packages/schemas/src/news_schemas/audit.py](packages/schemas/src/news_schemas/audit.py)
- Test: `packages/schemas/src/news_schemas/tests/test_audit.py` (existing — append)

- [ ] **Step 1: Write the failing test**

Append to `packages/schemas/src/news_schemas/tests/test_audit.py`:

```python
from news_schemas.audit import AgentName, DecisionType


def test_audit_enum_extensions_for_api():
    # The API sub-project (#4) introduces these.
    assert AgentName.API.value == "api"
    assert DecisionType.PROFILE_UPDATE.value == "profile_update"
    assert DecisionType.REMIX_TRIGGERED.value == "remix_triggered"
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest packages/schemas/src/news_schemas/tests/test_audit.py::test_audit_enum_extensions_for_api -v
```

Expected: FAIL with `AttributeError: API`.

- [ ] **Step 3: Extend the enums**

Edit `packages/schemas/src/news_schemas/audit.py`:

```python
class AgentName(StrEnum):
    DIGEST = "digest_agent"
    EDITOR = "editor_agent"
    EMAIL = "email_agent"
    WEB_SEARCH = "web_search_agent"
    API = "api"


class DecisionType(StrEnum):
    SUMMARY = "summary"
    RANK = "rank"
    INTRO = "intro"
    SEARCH_RESULT = "search_result"
    PROFILE_UPDATE = "profile_update"
    REMIX_TRIGGERED = "remix_triggered"
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest packages/schemas/src/news_schemas/tests/test_audit.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add packages/schemas/src/news_schemas/audit.py packages/schemas/src/news_schemas/tests/test_audit.py
git commit -m "feat(schemas): AgentName.API + PROFILE_UPDATE/REMIX_TRIGGERED decision types"
```

---

## Phase 1 — DB extension

### Task 1.1: `DigestRepository.get_for_user(user_id, limit, before)` cursor-paginated method

**Files:**
- Modify: [packages/db/src/news_db/repositories/digest_repo.py](packages/db/src/news_db/repositories/digest_repo.py)
- Modify: [tests/integration/conftest.py](tests/integration/conftest.py) — add a `db_session_factory` fixture used by this test and the API integration tests.
- Test: `tests/integration/test_digest_repo_pagination.py` (new)

- [ ] **Step 1: Add `db_session_factory` fixture to the shared conftest**

The existing conftest exposes a per-test `session` fixture (single session that gets truncated at teardown). Tests that need to insert-then-query in *separate* sessions (to bypass the ORM's identity map and verify durability) need a factory. Add it alongside the existing `session` fixture in `tests/integration/conftest.py`:

```python
from collections.abc import Callable

@pytest_asyncio.fixture
async def db_session_factory(
    pg_container: PostgresContainer,
) -> AsyncIterator[Callable[[], AsyncSession]]:
    """Factory that yields fresh sessions on demand.

    Used by tests that need multiple short-lived sessions in one test
    (seed → API call → verify side-effect). Truncates all tables at
    teardown, like the per-test `session` fixture.
    """
    engine = create_async_engine(
        os.environ["SUPABASE_POOLER_URL"],
        connect_args={"statement_cache_size": 0},
    )
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "truncate table audit_logs, email_sends, digests, articles, scraper_runs, users "
                "restart identity cascade"
            )
        )
    await engine.dispose()
```

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/test_digest_repo_pagination.py`:

```python
"""Integration test for DigestRepository.get_for_user — cursor pagination."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from news_db.engine import get_session
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus, RankedArticle
from news_schemas.user_profile import UserIn, UserProfile

pytestmark = pytest.mark.asyncio


async def _seed_user(session) -> uuid4:
    repo = UserRepository(session)
    user = await repo.upsert_by_clerk_id(UserIn(
        clerk_user_id=f"user_{uuid4().hex[:8]}",
        email=f"u_{uuid4().hex[:8]}@example.com",
        name="Test User",
        email_name="Test",
        profile=UserProfile.empty(),
        profile_completed_at=datetime.now(timezone.utc),
    ))
    return user.id


def _digest_in(user_id, n: int) -> DigestIn:
    return DigestIn(
        user_id=user_id,
        period_start=datetime(2026, 4, n, tzinfo=timezone.utc),
        period_end=datetime(2026, 4, n + 1, tzinfo=timezone.utc),
        intro=f"day-{n}",
        ranked_articles=[],
        top_themes=[],
        article_count=0,
        status=DigestStatus.GENERATED,
    )


async def test_get_for_user_returns_desc_by_id_paged(db_session_factory):
    async with db_session_factory() as session:
        user_id = await _seed_user(session)
        repo = DigestRepository(session)
        # Insert 5 digests; their ids will be monotonically increasing.
        ids = [(await repo.create(_digest_in(user_id, n))).id for n in range(1, 6)]

    # Page 1: limit=2, before=None → returns the two most recent.
    async with db_session_factory() as session:
        page1 = await DigestRepository(session).get_for_user(user_id, limit=2, before=None)
    assert [d.id for d in page1] == [ids[4], ids[3]]
    assert "ranked_articles" not in page1[0].model_dump()  # confirm it's the summary

    # Page 2: limit=2, before=page1[-1].id
    async with db_session_factory() as session:
        page2 = await DigestRepository(session).get_for_user(user_id, limit=2, before=page1[-1].id)
    assert [d.id for d in page2] == [ids[2], ids[1]]

    # Page 3: limit=2, before=page2[-1].id → only 1 row remains.
    async with db_session_factory() as session:
        page3 = await DigestRepository(session).get_for_user(user_id, limit=2, before=page2[-1].id)
    assert [d.id for d in page3] == [ids[0]]


async def test_get_for_user_isolates_users(db_session_factory):
    async with db_session_factory() as session:
        a = await _seed_user(session)
        b = await _seed_user(session)
        repo = DigestRepository(session)
        await repo.create(_digest_in(a, 1))
        await repo.create(_digest_in(b, 2))

    async with db_session_factory() as session:
        a_digests = await DigestRepository(session).get_for_user(a, limit=10, before=None)
        b_digests = await DigestRepository(session).get_for_user(b, limit=10, before=None)
    assert {d.user_id for d in a_digests} == {a}
    assert {d.user_id for d in b_digests} == {b}
```

(Reuses the existing `db_session_factory` fixture in `tests/integration/conftest.py` — testcontainers-postgres + alembic upgrade.)

- [ ] **Step 3: Run test to verify it fails**

```sh
uv run pytest tests/integration/test_digest_repo_pagination.py -v
```

Expected: FAIL with `AttributeError: 'DigestRepository' object has no attribute 'get_for_user'`.

- [ ] **Step 4: Implement the method**

Edit `packages/db/src/news_db/repositories/digest_repo.py`. Add new imports if needed (`DigestSummaryOut`) and append the method:

```python
from news_schemas.digest import DigestIn, DigestOut, DigestStatus, DigestSummaryOut

# ... existing class and methods ...

    async def get_for_user(
        self,
        user_id: UUID,
        limit: int,
        before: int | None = None,
    ) -> list[DigestSummaryOut]:
        """Cursor-paginated list of a user's digests, newest first.

        `before` is exclusive — pass the id of the last item from the previous
        page (or None for the first page). Excludes `ranked_articles` from the
        projection (see DigestSummaryOut).
        """
        stmt = select(Digest).where(Digest.user_id == user_id)
        if before is not None:
            stmt = stmt.where(Digest.id < before)
        stmt = stmt.order_by(Digest.id.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [DigestSummaryOut.model_validate(r, from_attributes=True) for r in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

```sh
uv run pytest tests/integration/test_digest_repo_pagination.py -v
```

Expected: both pass.

- [ ] **Step 6: Commit**

```sh
git add packages/db/src/news_db/repositories/digest_repo.py tests/integration/conftest.py tests/integration/test_digest_repo_pagination.py
git commit -m "feat(db): DigestRepository.get_for_user with cursor pagination + shared db_session_factory fixture"
```

---

## Phase 2 — Workspace scaffold

### Task 2.1: Create `services/api/` package skeleton

**Files:**
- Create: `services/api/pyproject.toml`
- Create: `services/api/src/news_api/__init__.py` (empty)
- Modify: [pyproject.toml](pyproject.toml) (root) — register member + source.

- [ ] **Step 1: Create the workspace package's `pyproject.toml`**

```sh
mkdir -p services/api/src/news_api
touch services/api/src/news_api/__init__.py
```

Create `services/api/pyproject.toml`:

```toml
[project]
name = "news_api"
version = "0.1.0"
requires-python = ">=3.12"
description = "API + Auth service — FastAPI on Lambda + Clerk JWT validation"
dependencies = [
    "fastapi>=0.115",
    "mangum>=0.19",
    "pyjwt[crypto]>=2.9",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.5",
    "loguru>=0.7.3",
    "typer>=0.24.2",
    "uvicorn>=0.30",
    "httpx>=0.28.1",
    "boto3>=1.42.95",
    "news_schemas",
    "news_config",
    "news_observability",
    "news_db",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/news_api"]
```

- [ ] **Step 2: Register the workspace member + source in root `pyproject.toml`**

Edit the root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "packages/schemas",
    "packages/config",
    "packages/observability",
    "packages/db",
    "services/scraper",
    "services/agents/digest",
    "services/agents/editor",
    "services/agents/email",
    "services/scheduler",
    "services/api",
]

[tool.uv.sources]
news_schemas = { workspace = true }
news_config = { workspace = true }
news_observability = { workspace = true }
news_db = { workspace = true }
news_scraper = { workspace = true }
news_digest = { workspace = true }
news_editor = { workspace = true }
news_email = { workspace = true }
news_scheduler = { workspace = true }
news_api = { workspace = true }
```

- [ ] **Step 3: Verify uv picks it up**

```sh
uv sync --all-packages
```

Expected: succeeds, no errors. Verify the package is recognised:

```sh
uv pip list | grep news_api
```

Expected: `news_api  0.1.0  (editable)`.

- [ ] **Step 4: Commit**

```sh
git add services/api/pyproject.toml services/api/src/news_api/__init__.py pyproject.toml uv.lock
git commit -m "feat(api): scaffold news_api workspace package + register in tooling"
```

---

## Phase 3 — Auth core (pure logic, unit-tested)

### Task 3.1: `ApiSettings` — env-backed configuration

**Files:**
- Create: `services/api/src/news_api/settings.py`
- Create: `services/api/src/news_api/tests/__init__.py` (empty)
- Create: `services/api/src/news_api/tests/unit/__init__.py` (empty)
- Test: `services/api/src/news_api/tests/unit/test_settings.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/unit/test_settings.py`:

```python
"""ApiSettings env loading."""

import pytest

from news_api.settings import ApiSettings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://test.clerk.dev")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")
    monkeypatch.setenv("REMIX_STATE_MACHINE_ARN",
                       "arn:aws:states:us-east-1:111111111111:stateMachine:news-remix-user-dev")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000,https://example.com")
    monkeypatch.setenv("GIT_SHA", "abc123")

    s = ApiSettings()
    assert s.clerk_issuer == "https://test.clerk.dev"
    assert s.clerk_jwks_url == "https://test.clerk.dev/.well-known/jwks.json"
    assert s.remix_state_machine_arn.endswith(":news-remix-user-dev")
    assert s.allowed_origins == ["http://localhost:3000", "https://example.com"]
    assert s.git_sha == "abc123"


def test_settings_allowed_origins_defaults_to_localhost(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://test.clerk.dev")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")
    monkeypatch.setenv("REMIX_STATE_MACHINE_ARN",
                       "arn:aws:states:us-east-1:111111111111:stateMachine:news-remix-user-dev")
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)

    s = ApiSettings()
    assert s.allowed_origins == ["http://localhost:3000"]
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_settings.py -v
```

Expected: FAIL with `ImportError: cannot import name 'ApiSettings'`.

- [ ] **Step 3: Implement settings**

Create `services/api/src/news_api/settings.py`:

```python
"""ApiSettings: env-backed configuration for the API service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    clerk_issuer: str = Field(
        ..., description="Clerk frontend API URL — used as the JWT 'iss' claim.",
    )
    clerk_jwks_url: str = Field(
        ..., description="Where to fetch Clerk's signing keys.",
    )
    remix_state_machine_arn: str = Field(
        ..., description="ARN of news-remix-user state machine (from #3).",
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="CORS allowed origins (also configured at API Gateway).",
    )
    git_sha: str = Field(default="unknown", description="Surfaced via /healthz.")
    log_level: str = Field(default="INFO")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        # Lambda env vars are strings; turn comma-separated into a list.
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Cached settings loader — one instance per process."""
    return ApiSettings()
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_settings.py -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/settings.py services/api/src/news_api/tests/
git commit -m "feat(api): ApiSettings (CLERK_*, REMIX_*, ALLOWED_ORIGINS, GIT_SHA)"
```

---

### Task 3.2: `ClerkClaims` model + `InvalidKid` exception

**Files:**
- Create: `services/api/src/news_api/auth/__init__.py` (empty)
- Create: `services/api/src/news_api/auth/verify.py` (model + exception only — no verify function yet)
- Test: `services/api/src/news_api/tests/unit/test_verify.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/unit/test_verify.py`:

```python
"""Unit tests for ClerkClaims and InvalidKid."""

import pytest

from news_api.auth.verify import ClerkClaims, InvalidKid


def test_clerk_claims_minimum_required():
    claims = ClerkClaims.model_validate({
        "sub": "user_abc",
        "email": "alice@example.com",
        "name": "Alice Smith",
        "exp": 1_777_777_777,
        "iat": 1_777_777_000,
        "iss": "https://test.clerk.dev",
    })
    assert claims.sub == "user_abc"
    assert claims.email == "alice@example.com"
    assert claims.name == "Alice Smith"
    assert claims.azp is None  # optional


def test_clerk_claims_rejects_invalid_email():
    with pytest.raises(Exception):  # pydantic.ValidationError
        ClerkClaims.model_validate({
            "sub": "user_abc",
            "email": "not-an-email",
            "name": "Alice",
            "exp": 1_777_777_777,
            "iat": 1_777_777_000,
            "iss": "https://test.clerk.dev",
        })


def test_invalid_kid_is_exception_subclass():
    assert issubclass(InvalidKid, Exception)
    raised = InvalidKid("kid 'foo' not in JWKS")
    assert "foo" in str(raised)
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_verify.py -v
```

Expected: FAIL with `ImportError: cannot import name 'ClerkClaims'`.

- [ ] **Step 3: Implement model + exception**

Create `services/api/src/news_api/auth/__init__.py` (empty file).

Create `services/api/src/news_api/auth/verify.py`:

```python
"""Clerk JWT verification primitives.

Exposes:
    ClerkClaims — Pydantic model of the JWT payload we care about.
    InvalidKid — raised when the JWT's `kid` header is not in the cached JWKS.
    verify_clerk_jwt — pure function (added in Task 3.3).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class InvalidKid(Exception):
    """Token's kid header doesn't match any cached JWK."""


class ClerkClaims(BaseModel):
    """Subset of Clerk's JWT payload that we use.

    Clerk's JWT can carry many more claims (org_id, session_id, etc.); we
    only validate the ones the API needs. Extra fields are ignored, not
    forbidden — Clerk will add fields over time.
    """

    model_config = ConfigDict(extra="ignore")

    sub: str
    email: EmailStr
    name: str
    exp: int
    iat: int
    iss: str
    azp: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_verify.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/auth/ services/api/src/news_api/tests/unit/test_verify.py
git commit -m "feat(api): ClerkClaims model + InvalidKid exception"
```

---

### Task 3.3: `verify_clerk_jwt` function

**Files:**
- Modify: `services/api/src/news_api/auth/verify.py` (extend with the function)
- Modify: `services/api/src/news_api/tests/unit/test_verify.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `services/api/src/news_api/tests/unit/test_verify.py`:

```python
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from news_api.auth.verify import (
    ClerkClaims,
    InvalidKid,
    verify_clerk_jwt,
)


def _make_keypair(kid: str = "test-key-1"):
    privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pubkey = privkey.public_key()
    return privkey, {kid: pubkey}


def _sign(privkey, *, kid="test-key-1", **claim_overrides) -> str:
    claims = {
        "sub": "user_abc",
        "email": "alice@example.com",
        "name": "Alice",
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
        "iss": "https://test.clerk.dev",
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, privkey, algorithm="RS256", headers={"kid": kid})


def test_verify_clerk_jwt_happy_path():
    privkey, jwks = _make_keypair()
    token = _sign(privkey)
    claims = verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)
    assert isinstance(claims, ClerkClaims)
    assert claims.sub == "user_abc"


def test_verify_clerk_jwt_unknown_kid_raises_invalid_kid():
    privkey, jwks = _make_keypair(kid="other-key")
    token = _sign(privkey, kid="bogus-kid")
    with pytest.raises(InvalidKid):
        verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)


def test_verify_clerk_jwt_expired_raises_invalid_token():
    privkey, jwks = _make_keypair()
    token = _sign(privkey, exp=int(time.time()) - 60)
    with pytest.raises(jwt.ExpiredSignatureError):
        verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)


def test_verify_clerk_jwt_wrong_issuer_raises_invalid_token():
    privkey, jwks = _make_keypair()
    token = _sign(privkey, iss="https://attacker.example.com")
    with pytest.raises(jwt.InvalidIssuerError):
        verify_clerk_jwt(token, jwks, issuer="https://test.clerk.dev", audience=None)


def test_verify_clerk_jwt_rejects_hs256_attack():
    """Algorithm-confusion attack — HS256 forged with public key as shared secret.

    Defended by hard-coding ['RS256'] in the algorithm whitelist.
    """
    privkey, jwks = _make_keypair()
    pubkey_pem = list(jwks.values())[0].public_bytes(
        encoding=__import__("cryptography").hazmat.primitives.serialization.Encoding.PEM,
        format=__import__("cryptography").hazmat.primitives.serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    forged = jwt.encode(
        {"sub": "user_abc", "email": "alice@example.com", "name": "A",
         "iat": int(time.time()), "exp": int(time.time()) + 600,
         "iss": "https://test.clerk.dev"},
        pubkey_pem,
        algorithm="HS256",
        headers={"kid": "test-key-1"},
    )
    with pytest.raises(jwt.InvalidAlgorithmError):
        verify_clerk_jwt(forged, jwks, issuer="https://test.clerk.dev", audience=None)
```

- [ ] **Step 2: Run tests to verify they fail**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_verify.py -v
```

Expected: FAIL with `ImportError: cannot import name 'verify_clerk_jwt'`.

- [ ] **Step 3: Implement the verifier**

Edit `services/api/src/news_api/auth/verify.py`. Append:

```python
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


def verify_clerk_jwt(
    token: str,
    jwks: dict[str, RSAPublicKey],
    issuer: str,
    audience: str | None,
) -> ClerkClaims:
    """Validate a Clerk-issued JWT.

    Args:
        token: The raw JWT string from the `Authorization: Bearer <token>` header.
        jwks: Map of `kid` → RSA public key, populated by `auth.jwks.get_jwks`.
        issuer: Expected `iss` claim — must match exactly.
        audience: Expected `aud` claim, or `None` to skip validation.

    Raises:
        InvalidKid: The token's kid header is not in the JWKS.
        jwt.InvalidTokenError (and subclasses): signature, issuer, audience,
            or expiration check failed.
    """
    headers = jwt.get_unverified_header(token)
    kid = headers.get("kid")
    if kid is None or kid not in jwks:
        raise InvalidKid(f"kid {kid!r} not in JWKS")
    payload = jwt.decode(
        token,
        jwks[kid],
        algorithms=["RS256"],  # whitelist defeats algorithm-confusion attacks
        issuer=issuer,
        audience=audience,
        options={"require": ["exp", "iat", "iss", "sub"]},
    )
    return ClerkClaims.model_validate(payload)
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_verify.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/auth/verify.py services/api/src/news_api/tests/unit/test_verify.py
git commit -m "feat(api): verify_clerk_jwt — RS256-only whitelist + JWKS lookup"
```

---

### Task 3.4: JWKS module — `get_jwks` + `reset_jwks`

**Files:**
- Create: `services/api/src/news_api/auth/jwks.py`
- Test: `services/api/src/news_api/tests/unit/test_jwks.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/unit/test_jwks.py`:

```python
"""Unit tests for the JWKS cache."""

from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from news_api.auth import jwks as jwks_module


def _b64u(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return urlsafe_b64encode(raw).rstrip(b"=").decode()


def _public_jwk(pubkey, *, kid: str = "key-1") -> dict:
    nums = pubkey.public_numbers()
    return {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
            "n": _b64u(nums.n), "e": _b64u(nums.e)}


def _jwks_payload(*pubkeys_with_kids) -> dict:
    return {"keys": [_public_jwk(p, kid=k) for p, k in pubkeys_with_kids]}


@pytest.fixture(autouse=True)
def _reset():
    jwks_module.reset_jwks()
    yield
    jwks_module.reset_jwks()


async def test_get_jwks_fetches_once_and_caches():
    pub = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    payload = _jwks_payload((pub, "key-1"))

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        out1 = await jwks_module.get_jwks(client, "https://test/jwks")
        out2 = await jwks_module.get_jwks(client, "https://test/jwks")

    assert isinstance(out1["key-1"], RSAPublicKey)
    assert out1 is out2  # cached identity


async def test_reset_jwks_forces_refresh():
    pub1 = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    pub2 = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    payloads = iter([_jwks_payload((pub1, "key-1")), _jwks_payload((pub2, "key-2"))])

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(payloads))

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        first = await jwks_module.get_jwks(client, "https://test/jwks")
        assert "key-1" in first
        jwks_module.reset_jwks()
        second = await jwks_module.get_jwks(client, "https://test/jwks")
        assert "key-2" in second
        assert "key-1" not in second
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_jwks.py -v
```

Expected: FAIL with `ImportError: cannot import name 'get_jwks'`.

- [ ] **Step 3: Implement the cache**

Create `services/api/src/news_api/auth/jwks.py`:

```python
"""JWKS fetcher with a per-cold-start cache.

Module-level state ties cache lifetime to the Lambda container's lifetime —
new container = new cache, exactly what we want. Reset only fires in tests
or in response to a forced refresh (e.g., after a JWKS-rotation 401).
"""

from __future__ import annotations

from base64 import urlsafe_b64decode

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPublicKey,
    RSAPublicNumbers,
)

_jwks: dict[str, RSAPublicKey] | None = None


def reset_jwks() -> None:
    """Drop the cache. Useful in tests and on forced JWKS refresh."""
    global _jwks
    _jwks = None


async def get_jwks(client: httpx.AsyncClient, url: str) -> dict[str, RSAPublicKey]:
    """Fetch + cache the JWKS for the container's life."""
    global _jwks
    if _jwks is None:
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        _jwks = {k["kid"]: _rsa_pub_from_jwk(k) for k in resp.json()["keys"]}
    return _jwks


def _rsa_pub_from_jwk(jwk: dict) -> RSAPublicKey:
    """Convert a JWK to an RSA public key. Only RS256 keys are supported."""
    n = int.from_bytes(_b64u_decode(jwk["n"]), "big")
    e = int.from_bytes(_b64u_decode(jwk["e"]), "big")
    return RSAPublicNumbers(e=e, n=n).public_key()


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + pad)
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_jwks.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/auth/jwks.py services/api/src/news_api/tests/unit/test_jwks.py
git commit -m "feat(api): JWKS fetcher + per-cold-start cache (get_jwks/reset_jwks)"
```

---

## Phase 4 — FastAPI app + routes

### Task 4.1: `app.py` factory + `routes/healthz.py` + integration test

**Files:**
- Create: `services/api/src/news_api/app.py`
- Create: `services/api/src/news_api/routes/__init__.py` (empty)
- Create: `services/api/src/news_api/routes/healthz.py`
- Create: `services/api/src/news_api/tests/integration/__init__.py` (empty)
- Create: `services/api/src/news_api/tests/integration/conftest.py`
- Create: `services/api/src/news_api/tests/integration/test_healthz.py`

- [ ] **Step 1: Write the failing test + conftest**

Create `services/api/src/news_api/tests/integration/conftest.py`:

```python
"""Integration test fixtures: ASGI client + monkeypatched settings.

`api_client` depends on `pg_container` from the shared
tests/integration/conftest.py — that fixture boots Postgres in Docker,
sets SUPABASE_* env vars, and runs Alembic. Session-scoped so the cost
is paid once per test session, even though /healthz doesn't need DB.

The JWT keypair / signed_jwt / patch_jwks fixtures land in Task 4.2
when get_current_user arrives.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer


@pytest.fixture
def api_settings_env(monkeypatch):
    monkeypatch.setenv("CLERK_ISSUER", "https://test.clerk.dev")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.dev/.well-known/jwks.json")
    monkeypatch.setenv("REMIX_STATE_MACHINE_ARN",
                       "arn:aws:states:us-east-1:111111111111:stateMachine:news-remix-user-dev")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("GIT_SHA", "test-sha")
    from news_api.settings import get_api_settings
    get_api_settings.cache_clear()


@pytest_asyncio.fixture
async def api_client(api_settings_env, pg_container: PostgresContainer):
    """ASGI client wired to the testcontainer Postgres."""
    from news_db import engine as engine_module
    from news_api.app import create_app

    engine_module.reset_engine()
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    engine_module.reset_engine()
```

Create `services/api/src/news_api/tests/integration/test_healthz.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_healthz_returns_ok(api_client):
    resp = await api_client.get("/v1/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "git_sha": "test-sha"}


async def test_healthz_does_not_require_auth(api_client):
    resp = await api_client.get("/v1/healthz")  # no Authorization header
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_healthz.py -v
```

Expected: FAIL with `ImportError: cannot import name 'create_app'`.

- [ ] **Step 3: Implement app + healthz**

Create `services/api/src/news_api/routes/__init__.py` (empty).

Create `services/api/src/news_api/routes/healthz.py`:

```python
"""Health probe — no auth, returns deploy-time git_sha."""

from __future__ import annotations

from fastapi import APIRouter

from news_api.settings import get_api_settings

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "git_sha": get_api_settings().git_sha}
```

Create `services/api/src/news_api/app.py`:

```python
"""FastAPI app factory — mounted under /v1."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from news_api.routes import healthz
from news_api.settings import get_api_settings


def create_app() -> FastAPI:
    settings = get_api_settings()
    app = FastAPI(title="news-api", version="0.5.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "PUT", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=3600,
    )
    app.include_router(healthz.router, prefix="/v1")
    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_healthz.py -v
```

Expected: both pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/app.py services/api/src/news_api/routes/ services/api/src/news_api/tests/integration/
git commit -m "feat(api): FastAPI app factory + /v1/healthz route"
```

---

### Task 4.2: `deps.py` — session + audit-logger + `get_current_user`

**Files:**
- Create: `services/api/src/news_api/deps.py`
- Modify: `services/api/src/news_api/tests/integration/conftest.py` (add JWT/JWKS fixtures)

- [ ] **Step 1: Extend the integration conftest with JWT helpers**

Edit `services/api/src/news_api/tests/integration/conftest.py`. Append after the existing fixtures:

```python
import time
from base64 import urlsafe_b64encode

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session")
def jwt_keypair():
    """One RSA keypair per test session — used to sign tokens locally."""
    privkey = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return privkey, privkey.public_key()


@pytest.fixture(autouse=True)
def patch_jwks(monkeypatch, jwt_keypair):
    """Replace the JWKS fetcher to return the test public key."""
    _, pubkey = jwt_keypair

    async def _fake_get_jwks(*_args, **_kwargs):
        return {"test-key-1": pubkey}

    from news_api.auth import jwks as jwks_module
    monkeypatch.setattr(jwks_module, "get_jwks", _fake_get_jwks)
    jwks_module.reset_jwks()


@pytest.fixture
def signed_jwt(jwt_keypair):
    privkey, _ = jwt_keypair

    def _sign(*, sub: str, email: str, name: str = "Test User",
              issuer: str = "https://test.clerk.dev",
              expires_in: int = 600) -> str:
        return jwt.encode({
            "sub": sub, "email": email, "name": name,
            "iat": int(time.time()),
            "exp": int(time.time()) + expires_in,
            "iss": issuer,
        }, privkey, algorithm="RS256", headers={"kid": "test-key-1"})

    return _sign


@pytest.fixture
def auth_header(signed_jwt):
    """Convenience: returns a function that produces an Authorization header dict."""
    def _header(*, sub: str, email: str = "alice@example.com", name: str = "Alice") -> dict:
        return {"Authorization": f"Bearer {signed_jwt(sub=sub, email=email, name=name)}"}
    return _header
```

- [ ] **Step 2: Implement deps**

Create `services/api/src/news_api/deps.py`:

```python
"""FastAPI dependencies: DB session, audit logger, current user."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from news_db.engine import get_session
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.user_repo import UserRepository
from news_observability.audit import AuditLogger
from news_schemas.user_profile import UserIn, UserOut, UserProfile
from sqlalchemy.ext.asyncio import AsyncSession

from news_api.auth.jwks import get_jwks
from news_api.auth.verify import InvalidKid, verify_clerk_jwt
from news_api.settings import get_api_settings

# Single httpx client per process — reused across requests for connection
# pooling. Lambda containers run one request at a time so this is safe.
_http_client = httpx.AsyncClient(timeout=5.0)


async def get_session_dep() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession scoped to the current request."""
    async with get_session() as session:
        yield session


def get_audit_logger(
    session: AsyncSession = Depends(get_session_dep),
) -> AuditLogger:
    """AuditLogger bound to the current request's DB session."""
    return AuditLogger(AuditLogRepository(session).insert)


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session_dep),
) -> UserOut:
    """Validate Clerk JWT and return (or lazy-create) the matching user.

    Sequence:
        1. Read Authorization: Bearer <token>.
        2. Ensure JWKS is cached for this container (lazy fetch).
        3. Verify signature + iss/exp/iat/sub against the cached JWK.
        4. Look up users.clerk_user_id; if missing, upsert from JWT claims.
    """
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    token = auth[7:]

    settings = get_api_settings()
    try:
        jwks = await get_jwks(_http_client, settings.clerk_jwks_url)
        claims = verify_clerk_jwt(token, jwks, settings.clerk_issuer, audience=None)
    except (InvalidKid, jwt.InvalidTokenError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token",
                            headers={"WWW-Authenticate": "Bearer"})

    repo = UserRepository(session)
    user = await repo.get_by_clerk_id(claims.sub)
    if user is not None:
        return user

    # Lazy upsert: first authenticated request from this Clerk user.
    return await repo.upsert_by_clerk_id(UserIn(
        clerk_user_id=claims.sub,
        email=claims.email,
        name=claims.name,
        email_name=claims.name.split()[0] if claims.name else "there",
        profile=UserProfile.empty(),
        profile_completed_at=None,
    ))
```

- [ ] **Step 3: Verify imports and lint**

```sh
uv run ruff check services/api/src/news_api/deps.py
uv run mypy packages services/api 2>&1 | tail -5
```

Expected: no errors.

- [ ] **Step 4: Commit**

```sh
git add services/api/src/news_api/deps.py services/api/src/news_api/tests/integration/conftest.py
git commit -m "feat(api): get_session_dep / get_audit_logger / get_current_user (lazy upsert)"
```

---

### Task 4.3: `routes/me.py` — `GET /me` + integration test

**Files:**
- Create: `services/api/src/news_api/routes/me.py` (GET only — PUT lands in 4.4)
- Modify: `services/api/src/news_api/app.py` — mount the router
- Test: `services/api/src/news_api/tests/integration/test_me.py`

The integration tests for me/profile/digests/remix routes need real Postgres. Reuse the testcontainers fixture from `tests/integration/conftest.py`. Add a session-scoped fixture in the api integration conftest that wires DB engine reset to the testcontainer URL.

- [ ] **Step 1: (Done in Task 4.1.)** The `api_client` fixture from Task 4.1 already depends on `pg_container`, so `/me` integration tests get a real testcontainer Postgres. The JWT helpers were appended in Task 4.2. Skip directly to writing the test.

- [ ] **Step 2: Write the failing test**

Create `services/api/src/news_api/tests/integration/test_me.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio


async def test_me_requires_bearer(api_client):
    resp = await api_client.get("/v1/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_me_rejects_invalid_token(api_client):
    resp = await api_client.get("/v1/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_me_lazy_creates_user_on_first_call(api_client, auth_header):
    resp = await api_client.get("/v1/me",
                                headers=auth_header(sub="user_first", email="first@x.com",
                                                    name="First User"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["clerk_user_id"] == "user_first"
    assert body["email"] == "first@x.com"
    assert body["name"] == "First User"
    assert body["email_name"] == "First"
    assert body["profile_completed_at"] is None
    # Profile is the empty default.
    assert body["profile"]["interests"]["primary"] == []


async def test_me_returns_existing_user_on_second_call(api_client, auth_header):
    h = auth_header(sub="user_second", email="second@x.com", name="Second")
    first = await api_client.get("/v1/me", headers=h)
    second = await api_client.get("/v1/me", headers=h)
    assert first.status_code == 200
    assert second.status_code == 200
    # Same DB row.
    assert first.json()["id"] == second.json()["id"]
```

- [ ] **Step 3: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_me.py -v
```

Expected: FAIL with `404 Not Found` (the route doesn't exist yet).

- [ ] **Step 4: Implement the route**

Create `services/api/src/news_api/routes/me.py`:

```python
"""User identity routes — GET /me, PUT /me/profile (PUT in Task 4.4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from news_schemas.user_profile import UserOut

from news_api.deps import get_current_user

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    return current_user
```

Edit `services/api/src/news_api/app.py` — mount the new router:

```python
from news_api.routes import healthz, me

# ... in create_app() after the healthz include:
    app.include_router(me.router, prefix="/v1")
```

- [ ] **Step 5: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_me.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```sh
git add services/api/src/news_api/routes/me.py services/api/src/news_api/app.py services/api/src/news_api/tests/integration/
git commit -m "feat(api): GET /v1/me with lazy upsert"
```

---

### Task 4.4: `routes/me.py` — `PUT /me/profile`

**Files:**
- Modify: `services/api/src/news_api/routes/me.py` — add PUT handler
- Test: `services/api/src/news_api/tests/integration/test_profile.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/integration/test_profile.py`:

```python
import pytest

pytestmark = pytest.mark.asyncio

_SAMPLE_PROFILE = {
    "background": ["AI engineer"],
    "interests": {
        "primary": ["LLMs", "agents"],
        "secondary": ["devops"],
        "specific_topics": ["MCP servers"],
    },
    "preferences": {
        "content_type": ["technical deep dives"],
        "avoid": ["press releases"],
    },
    "goals": ["stay current on agent infra"],
    "reading_time": {
        "daily_limit": "20 minutes",
        "preferred_article_count": "8",
    },
}


async def test_put_profile_first_completion_sets_timestamp(api_client, auth_header):
    h = auth_header(sub="user_pp1", email="pp1@x.com", name="Patty")
    # Lazy-create the user.
    await api_client.get("/v1/me", headers=h)

    resp = await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_completed_at"] is not None
    assert body["profile"]["interests"]["primary"] == ["LLMs", "agents"]


async def test_put_profile_second_call_does_not_re_set_completed_at(api_client, auth_header):
    h = auth_header(sub="user_pp2", email="pp2@x.com", name="Patty")
    await api_client.get("/v1/me", headers=h)

    first = await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)
    completed_at_first = first.json()["profile_completed_at"]
    assert completed_at_first is not None

    second_profile = {**_SAMPLE_PROFILE, "background": ["new bio"]}
    second = await api_client.put("/v1/me/profile", headers=h, json=second_profile)
    body = second.json()
    assert body["profile_completed_at"] == completed_at_first  # unchanged
    assert body["profile"]["background"] == ["new bio"]


async def test_put_profile_rejects_invalid_body(api_client, auth_header):
    h = auth_header(sub="user_pp3", email="pp3@x.com", name="Patty")
    await api_client.get("/v1/me", headers=h)

    bad_body = {"interests": {}}  # missing required nested fields
    resp = await api_client.put("/v1/me/profile", headers=h, json=bad_body)
    assert resp.status_code == 422


async def test_put_profile_writes_audit_row(api_client, auth_header, db_session_factory):
    from sqlalchemy import select

    from news_db.models.audit_log import AuditLog

    h = auth_header(sub="user_pp4", email="pp4@x.com", name="Patty")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    async with db_session_factory() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.decision_type == "profile_update")
        )).scalars().all()
    assert len(rows) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_profile.py -v
```

Expected: FAIL with 405 Method Not Allowed (route doesn't exist).

- [ ] **Step 3: Implement the PUT handler**

Edit `services/api/src/news_api/routes/me.py`. Append:

```python
from news_observability.audit import AuditLogger
from news_schemas.audit import AgentName, DecisionType
from news_schemas.user_profile import UserProfile
from news_db.engine import get_session
from news_db.repositories.user_repo import UserRepository

from news_api.deps import get_audit_logger, get_session_dep
from sqlalchemy.ext.asyncio import AsyncSession


@router.put("/me/profile", response_model=UserOut)
async def put_my_profile(
    profile: UserProfile,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
    audit: AuditLogger = Depends(get_audit_logger),
) -> UserOut:
    repo = UserRepository(session)
    updated = await repo.update_profile(current_user.id, profile)
    first_completion = current_user.profile_completed_at is None
    if first_completion:
        updated = await repo.mark_profile_complete(current_user.id)
    await audit.log_decision(
        agent_name=AgentName.API,
        user_id=current_user.id,
        decision_type=DecisionType.PROFILE_UPDATE,
        input_text=profile.model_dump_json(),
        output_text="ok",
        metadata={"first_completion": first_completion},
    )
    return updated
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_profile.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/routes/me.py services/api/src/news_api/tests/integration/test_profile.py
git commit -m "feat(api): PUT /v1/me/profile (full replace + first-completion flag)"
```

---

### Task 4.5: `routes/digests.py` — list + detail

**Files:**
- Create: `services/api/src/news_api/routes/digests.py`
- Modify: `services/api/src/news_api/app.py` — mount router
- Test: `services/api/src/news_api/tests/integration/test_digests.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/integration/test_digests.py`:

```python
"""Integration tests for /v1/digests list + detail."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.user_profile import UserIn, UserProfile

pytestmark = pytest.mark.asyncio


async def _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                   *, sub: str, email: str, n: int):
    """Lazy-create the user via /me, then seed N digests in the DB."""
    h = auth_header(sub=sub, email=email, name=email.split("@")[0])
    me = (await api_client.get("/v1/me", headers=h)).json()
    user_id = me["id"]
    async with db_session_factory() as session:
        repo = DigestRepository(session)
        for i in range(1, n + 1):
            await repo.create(DigestIn(
                user_id=user_id,
                period_start=datetime(2026, 4, i, tzinfo=timezone.utc),
                period_end=datetime(2026, 4, i + 1, tzinfo=timezone.utc),
                intro=f"day-{i}",
                ranked_articles=[],
                top_themes=[],
                article_count=0,
                status=DigestStatus.GENERATED,
            ))
    return h, user_id


async def test_digests_paginates(api_client, auth_header, db_session_factory):
    h, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                          sub="user_dl1", email="dl1@x.com", n=5)

    page1 = await api_client.get("/v1/digests?limit=2", headers=h)
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["next_before"] == body1["items"][-1]["id"]
    # Confirm summary projection — no ranked_articles in the response.
    assert "ranked_articles" not in body1["items"][0]

    page2 = await api_client.get(
        f"/v1/digests?limit=2&before={body1['next_before']}", headers=h,
    )
    body2 = page2.json()
    assert len(body2["items"]) == 2

    page3 = await api_client.get(
        f"/v1/digests?limit=2&before={body2['next_before']}", headers=h,
    )
    body3 = page3.json()
    assert len(body3["items"]) == 1
    assert body3["next_before"] is None


async def test_digests_isolates_users(api_client, auth_header, db_session_factory):
    h_a, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                            sub="user_dlA", email="dla@x.com", n=2)
    h_b, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                            sub="user_dlB", email="dlb@x.com", n=3)
    a = (await api_client.get("/v1/digests?limit=10", headers=h_a)).json()
    b = (await api_client.get("/v1/digests?limit=10", headers=h_b)).json()
    assert len(a["items"]) == 2
    assert len(b["items"]) == 3


async def test_digest_detail_owner_succeeds(api_client, auth_header, db_session_factory):
    h, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                          sub="user_dd1", email="dd1@x.com", n=1)
    listing = (await api_client.get("/v1/digests?limit=1", headers=h)).json()
    digest_id = listing["items"][0]["id"]

    resp = await api_client.get(f"/v1/digests/{digest_id}", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == digest_id
    assert "ranked_articles" in body  # full projection


async def test_digest_detail_other_user_404s(api_client, auth_header, db_session_factory):
    h_a, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                            sub="user_ddA", email="dda@x.com", n=1)
    h_b, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                            sub="user_ddB", email="ddb@x.com", n=1)
    listing_a = (await api_client.get("/v1/digests?limit=1", headers=h_a)).json()
    a_digest_id = listing_a["items"][0]["id"]

    resp = await api_client.get(f"/v1/digests/{a_digest_id}", headers=h_b)
    assert resp.status_code == 404


async def test_digest_detail_nonexistent_404s(api_client, auth_header, db_session_factory):
    h, _ = await _ensure_user_and_digests(api_client, auth_header, db_session_factory,
                                          sub="user_ddX", email="ddx@x.com", n=0)
    resp = await api_client.get("/v1/digests/999999999", headers=h)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_digests.py -v
```

Expected: FAIL with 404 Not Found (route absent).

- [ ] **Step 3: Implement the routes**

Create `services/api/src/news_api/routes/digests.py`:

```python
"""Digest list + detail routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from news_db.repositories.digest_repo import DigestRepository
from news_schemas.digest import DigestOut, DigestSummaryOut
from news_schemas.user_profile import UserOut
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from news_api.deps import get_current_user, get_session_dep

router = APIRouter()


class DigestListResponse(BaseModel):
    items: list[DigestSummaryOut]
    next_before: int | None


@router.get("/digests", response_model=DigestListResponse)
async def list_digests(
    limit: int = Query(default=10, ge=1, le=50),
    before: int | None = Query(default=None, ge=1),
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> DigestListResponse:
    repo = DigestRepository(session)
    items = await repo.get_for_user(current_user.id, limit=limit, before=before)
    next_before = items[-1].id if len(items) == limit else None
    return DigestListResponse(items=items, next_before=next_before)


@router.get("/digests/{digest_id}", response_model=DigestOut)
async def get_digest(
    digest_id: int,
    current_user: UserOut = Depends(get_current_user),
    session: AsyncSession = Depends(get_session_dep),
) -> DigestOut:
    repo = DigestRepository(session)
    digest = await repo.get_by_id(digest_id)
    # Same 404 for nonexistent and not-mine — don't leak existence.
    if digest is None or digest.user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "digest not found")
    return digest
```

Edit `services/api/src/news_api/app.py` — mount the new router:

```python
from news_api.routes import digests, healthz, me

# ... include_router calls:
    app.include_router(digests.router, prefix="/v1")
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_digests.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/routes/digests.py services/api/src/news_api/app.py services/api/src/news_api/tests/integration/test_digests.py
git commit -m "feat(api): GET /v1/digests + GET /v1/digests/{id} with cursor pagination"
```

---

## Phase 5 — Remix endpoint

### Task 5.1: `clients/stepfunctions.py` — `start_remix` wrapper

**Files:**
- Create: `services/api/src/news_api/clients/__init__.py` (empty)
- Create: `services/api/src/news_api/clients/stepfunctions.py`
- Test: `services/api/src/news_api/tests/unit/test_stepfunctions.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/unit/test_stepfunctions.py`:

```python
"""Unit tests for the start_remix boto3 wrapper."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from news_api.clients import stepfunctions as sfn_module


@pytest.fixture(autouse=True)
def _clear_client_cache():
    sfn_module._sfn_client.cache_clear()
    yield
    sfn_module._sfn_client.cache_clear()


async def test_start_remix_passes_payload_correctly(monkeypatch):
    fake_client = MagicMock()
    fake_client.start_execution.return_value = {
        "executionArn": "arn:aws:states:us-east-1:111:execution:news-remix-user-dev:abc",
        "startDate": datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc),
    }
    monkeypatch.setattr(sfn_module, "_sfn_client", lambda: fake_client)

    user_id = uuid4()
    arn, started = await sfn_module.start_remix(
        state_machine_arn="arn:aws:states:us-east-1:111:stateMachine:news-remix-user-dev",
        user_id=user_id,
        lookback_hours=12,
    )
    assert arn.endswith(":abc")
    assert started.isoformat() == "2026-04-27T10:00:00+00:00"

    fake_client.start_execution.assert_called_once()
    call_kwargs = fake_client.start_execution.call_args.kwargs
    assert call_kwargs["stateMachineArn"].endswith(":news-remix-user-dev")
    payload = json.loads(call_kwargs["input"])
    assert payload == {"user_id": str(user_id), "lookback_hours": 12}
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_stepfunctions.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'news_api.clients'`.

- [ ] **Step 3: Implement the wrapper**

Create `services/api/src/news_api/clients/__init__.py` (empty).

Create `services/api/src/news_api/clients/stepfunctions.py`:

```python
"""Thin wrapper around boto3's Step Functions client for start_remix.

Single source of truth for `import boto3` in the API service.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from functools import lru_cache
from uuid import UUID

import boto3


@lru_cache(maxsize=1)
def _sfn_client():
    """One client per warm container — same lifetime as runtime credentials."""
    return boto3.client("stepfunctions")


async def start_remix(
    *,
    state_machine_arn: str,
    user_id: UUID,
    lookback_hours: int,
) -> tuple[str, datetime]:
    """Trigger news-remix-user with `{user_id, lookback_hours}` input.

    Returns (executionArn, startDate). boto3 is sync, so we offload to a
    worker thread to avoid blocking the asyncio event loop.
    """
    payload = json.dumps({
        "user_id": str(user_id),
        "lookback_hours": lookback_hours,
    })
    resp = await asyncio.to_thread(
        _sfn_client().start_execution,
        stateMachineArn=state_machine_arn,
        input=payload,
    )
    return resp["executionArn"], resp["startDate"]
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/unit/test_stepfunctions.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/clients/ services/api/src/news_api/tests/unit/test_stepfunctions.py
git commit -m "feat(api): start_remix boto3 wrapper (Step Functions client)"
```

---

### Task 5.2: `routes/remix.py` — `POST /remix`

**Files:**
- Create: `services/api/src/news_api/routes/remix.py`
- Modify: `services/api/src/news_api/app.py` — mount router
- Test: `services/api/src/news_api/tests/integration/test_remix.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/src/news_api/tests/integration/test_remix.py`:

```python
"""Integration tests for POST /v1/remix."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio

_SAMPLE_PROFILE = {
    "background": ["AI engineer"],
    "interests": {"primary": ["LLMs"], "secondary": [], "specific_topics": []},
    "preferences": {"content_type": [], "avoid": []},
    "goals": [],
    "reading_time": {"daily_limit": "20 minutes", "preferred_article_count": "8"},
}


@pytest.fixture
def mock_start_remix(monkeypatch):
    """Replace start_remix with a recording AsyncMock."""
    from news_api.routes import remix as remix_module
    mock = AsyncMock(return_value=(
        "arn:aws:states:us-east-1:111:execution:news-remix-user-dev:test-exec-1",
        datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc),
    ))
    monkeypatch.setattr(remix_module, "start_remix", mock)
    return mock


async def test_remix_409_when_profile_incomplete(api_client, auth_header, mock_start_remix):
    h = auth_header(sub="user_rx1", email="rx1@x.com", name="R")
    await api_client.get("/v1/me", headers=h)  # lazy-creates with empty profile

    resp = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 24})
    assert resp.status_code == 409
    assert resp.json()["error"] == "profile_incomplete"
    mock_start_remix.assert_not_called()


async def test_remix_202_starts_execution_with_correct_payload(api_client, auth_header,
                                                                mock_start_remix):
    h = auth_header(sub="user_rx2", email="rx2@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    resp = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 12})
    assert resp.status_code == 202
    body = resp.json()
    assert body["execution_arn"].endswith(":test-exec-1")
    assert body["started_at"] == "2026-04-27T10:00:00+00:00"

    mock_start_remix.assert_called_once()
    call_kwargs = mock_start_remix.call_args.kwargs
    assert call_kwargs["lookback_hours"] == 12
    assert isinstance(call_kwargs["user_id"].hex, str)


async def test_remix_default_lookback_hours_is_24(api_client, auth_header, mock_start_remix):
    h = auth_header(sub="user_rx3", email="rx3@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    resp = await api_client.post("/v1/remix", headers=h, json={})
    assert resp.status_code == 202
    assert mock_start_remix.call_args.kwargs["lookback_hours"] == 24


async def test_remix_rejects_lookback_out_of_range(api_client, auth_header, mock_start_remix):
    h = auth_header(sub="user_rx4", email="rx4@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    too_small = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 0})
    too_big = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 200})
    assert too_small.status_code == 422
    assert too_big.status_code == 422
    mock_start_remix.assert_not_called()


async def test_remix_writes_audit_row(api_client, auth_header, mock_start_remix,
                                       db_session_factory):
    from sqlalchemy import select

    from news_db.models.audit_log import AuditLog

    h = auth_header(sub="user_rx5", email="rx5@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)
    await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 6})

    async with db_session_factory() as session:
        rows = (await session.execute(
            select(AuditLog).where(AuditLog.decision_type == "remix_triggered")
        )).scalars().all()
    assert len(rows) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_remix.py -v
```

Expected: FAIL with 404 Not Found.

- [ ] **Step 3: Implement the route**

Create `services/api/src/news_api/routes/remix.py`:

```python
"""POST /v1/remix — trigger news-remix-user state machine."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from news_observability.audit import AuditLogger
from news_schemas.audit import AgentName, DecisionType
from news_schemas.user_profile import UserOut
from pydantic import BaseModel, Field

from news_api.clients.stepfunctions import start_remix
from news_api.deps import get_audit_logger, get_current_user
from news_api.settings import get_api_settings

router = APIRouter()


class RemixRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=168)


class RemixResponse(BaseModel):
    execution_arn: str
    started_at: datetime


@router.post("/remix", response_model=RemixResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_remix(
    body: RemixRequest,
    current_user: UserOut = Depends(get_current_user),
    audit: AuditLogger = Depends(get_audit_logger),
) -> RemixResponse:
    if current_user.profile_completed_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            detail={"error": "profile_incomplete"})

    settings = get_api_settings()
    arn, started = await start_remix(
        state_machine_arn=settings.remix_state_machine_arn,
        user_id=current_user.id,
        lookback_hours=body.lookback_hours,
    )
    await audit.log_decision(
        agent_name=AgentName.API,
        user_id=current_user.id,
        decision_type=DecisionType.REMIX_TRIGGERED,
        input_text=f"lookback_hours={body.lookback_hours}",
        output_text=arn,
        metadata={"execution_arn": arn, "lookback_hours": body.lookback_hours},
    )
    return RemixResponse(execution_arn=arn, started_at=started)
```

Edit `services/api/src/news_api/app.py` — mount the router:

```python
from news_api.routes import digests, healthz, me, remix

# ... include_router calls:
    app.include_router(remix.router, prefix="/v1")
```

- [ ] **Step 4: Run tests to verify they pass**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_remix.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```sh
git add services/api/src/news_api/routes/remix.py services/api/src/news_api/app.py services/api/src/news_api/tests/integration/test_remix.py
git commit -m "feat(api): POST /v1/remix (409 if profile incomplete, audit + SFN start)"
```

---

### Task 5.3: JWT regression suite

**Files:**
- Test: `services/api/src/news_api/tests/integration/test_jwt_regression.py`

- [ ] **Step 1: Write the regression tests**

Create `services/api/src/news_api/tests/integration/test_jwt_regression.py`:

```python
"""End-to-end JWT-validation regressions: tampered, wrong issuer/algorithm, missing kid."""

from __future__ import annotations

import time
from base64 import urlsafe_b64encode

import jwt
import pytest

pytestmark = pytest.mark.asyncio


def _b64u(b: bytes) -> str:
    return urlsafe_b64encode(b).rstrip(b"=").decode()


async def test_wrong_issuer_returns_401(api_client, jwt_keypair):
    privkey, _ = jwt_keypair
    token = jwt.encode({
        "sub": "user_x", "email": "x@x.com", "name": "X",
        "iat": int(time.time()), "exp": int(time.time()) + 600,
        "iss": "https://attacker.example.com",
    }, privkey, algorithm="RS256", headers={"kid": "test-key-1"})
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_tampered_signature_returns_401(api_client, signed_jwt):
    token = signed_jwt(sub="user_x", email="x@x.com", name="X")
    # Flip the last character of the signature.
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {tampered}"})
    assert resp.status_code == 401


async def test_missing_kid_returns_401(api_client, jwt_keypair):
    privkey, _ = jwt_keypair
    token = jwt.encode({
        "sub": "user_x", "email": "x@x.com", "name": "X",
        "iat": int(time.time()), "exp": int(time.time()) + 600,
        "iss": "https://test.clerk.dev",
    }, privkey, algorithm="RS256")  # no headers={"kid": ...}
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_hs256_forgery_returns_401(api_client, jwt_keypair):
    """Algorithm-confusion: forge HS256 with public key bytes as shared secret."""
    from cryptography.hazmat.primitives import serialization

    _, pubkey = jwt_keypair
    pem = pubkey.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    forged = jwt.encode({
        "sub": "user_x", "email": "x@x.com", "name": "X",
        "iat": int(time.time()), "exp": int(time.time()) + 600,
        "iss": "https://test.clerk.dev",
    }, pem, algorithm="HS256", headers={"kid": "test-key-1"})
    resp = await api_client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests**

```sh
uv run pytest services/api/src/news_api/tests/integration/test_jwt_regression.py -v
```

Expected: all pass (verify_clerk_jwt already enforces these).

- [ ] **Step 3: Commit**

```sh
git add services/api/src/news_api/tests/integration/test_jwt_regression.py
git commit -m "test(api): JWT regression suite (issuer, signature, kid, algorithm)"
```

---

## Phase 6 — Lambda handler + CLI

### Task 6.1: `lambda_handler.py` — Mangum + reset_engine + cold-start

**Files:**
- Create: `services/api/lambda_handler.py`

- [ ] **Step 1: Implement the handler**

Create `services/api/lambda_handler.py`:

```python
"""AWS Lambda entry point for the API service.

Cold-start: hydrates env from SSM, configures logging + tracing, builds
the FastAPI app and the Mangum adapter once.

Per-invocation: calls reset_engine() before the ASGI dispatch — same
warm-start asyncio-loop fix as #2/#3 — then delegates to Mangum.
"""

from __future__ import annotations

import os
from typing import Any

from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from mangum import Mangum  # noqa: E402
from news_db.engine import reset_engine  # noqa: E402
from news_observability.logging import get_logger, setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

from news_api.app import create_app  # noqa: E402

_log = get_logger("lambda_handler")
setup_logging()
configure_tracing(enable_langfuse=True)

_app = create_app()
_asgi_handler = Mangum(_app, lifespan="off")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    # Drop the cached SQLAlchemy engine: each invocation runs through
    # asyncio under the hood, but the pool's asyncpg connections are bound
    # to whichever loop first opened them. On warm-start reuse, the old
    # loop is closed → "RuntimeError: ... attached to a different loop".
    reset_engine()
    return _asgi_handler(event, context)
```

- [ ] **Step 2: Smoke test the import path**

```sh
uv run python -c "from services.api.lambda_handler import handler; print('ok', handler.__name__)"
```

(Note: this won't run without SSM env. If you want a no-SSM smoke, `uv run python -c "from news_api.app import create_app; create_app(); print('ok')"`.)

Expected: prints `ok`.

- [ ] **Step 3: Commit**

```sh
git add services/api/lambda_handler.py
git commit -m "feat(api): lambda_handler — Mangum + reset_engine() + cold-start init"
```

---

### Task 6.2: `cli.py` + `__main__.py` — Typer `serve`

**Files:**
- Create: `services/api/src/news_api/cli.py`
- Create: `services/api/src/news_api/__main__.py`

- [ ] **Step 1: Implement CLI**

Create `services/api/src/news_api/cli.py`:

```python
"""Typer CLI — exposes `serve` for local uvicorn."""

from __future__ import annotations

import typer
import uvicorn

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _main() -> None:
    """news-api CLI."""


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = True) -> None:
    """Run the FastAPI app under uvicorn for local dev."""
    uvicorn.run("news_api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
```

Create `services/api/src/news_api/__main__.py`:

```python
"""Allows `python -m news_api …` to invoke the Typer CLI."""

from __future__ import annotations

from news_api.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Smoke test**

```sh
uv run python -m news_api --help
```

Expected: shows `serve` subcommand.

- [ ] **Step 3: Commit**

```sh
git add services/api/src/news_api/cli.py services/api/src/news_api/__main__.py
git commit -m "feat(api): Typer CLI with `serve` for local uvicorn"
```

---

## Phase 7 — Infra (Terraform)

### Task 7.1: Module skeleton — backend/data/variables/outputs

**Files:**
- Create: `infra/api/backend.tf`
- Create: `infra/api/data.tf`
- Create: `infra/api/variables.tf`
- Create: `infra/api/outputs.tf`
- Create: `infra/api/terraform.tfvars.example`
- Create: `infra/api/.gitignore`

- [ ] **Step 1: Create the files**

`infra/api/backend.tf`:

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
  backend "s3" {
    # Init: terraform init -backend-config="bucket=news-aggregator-tf-state-<acct>"
    #                      -backend-config="key=api/terraform.tfstate"
    #                      -backend-config="region=us-east-1"
    #                      -backend-config="profile=aiengineer"
    use_lockfile = true
  }
}

provider "aws" {
  region  = "us-east-1"
  profile = "aiengineer"
}
```

`infra/api/data.tf`:

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Cross-module read: the remix state-machine ARN created by infra/scheduler/.
data "terraform_remote_state" "scheduler" {
  backend = "s3"
  config = {
    bucket  = "news-aggregator-tf-state-${data.aws_caller_identity.current.account_id}"
    key     = "scheduler/terraform.tfstate"
    region  = "us-east-1"
    profile = "aiengineer"
  }
  workspace = terraform.workspace
}
```

`infra/api/variables.tf`:

```hcl
variable "zip_s3_key" {
  type        = string
  description = "S3 key under the lambda artefacts bucket — set by deploy.py."
}

variable "zip_sha256" {
  type        = string
  description = "Base64-encoded SHA-256 of the zip — set by deploy.py."
}

variable "git_sha" {
  type        = string
  description = "Surfaced via /v1/healthz."
  default     = "unknown"
}

variable "clerk_issuer" {
  type        = string
  description = "Clerk frontend API URL (e.g. https://clerk.example.com)."

  validation {
    condition     = startswith(var.clerk_issuer, "https://")
    error_message = "clerk_issuer must be HTTPS."
  }
}

variable "allowed_origins" {
  type        = list(string)
  description = "CORS allowed origins for both API Gateway and FastAPI middleware."
  default     = ["http://localhost:3000"]
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "memory_size" {
  type    = number
  default = 512
}

variable "timeout" {
  type    = number
  default = 15
}
```

`infra/api/outputs.tf`:

```hcl
output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "function_arn" {
  value = aws_lambda_function.api.arn
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.api.name
}

output "api_endpoint" {
  description = "Base URL for the HTTP API ($default stage)."
  value       = aws_apigatewayv2_api.api.api_endpoint
}
```

`infra/api/terraform.tfvars.example`:

```hcl
# Set these for `terraform apply` (or pass via -var on the command line).
zip_s3_key      = "api/<git-sha>.zip"
zip_sha256      = "<base64-sha256-of-zip>"
git_sha         = "<git-sha>"
clerk_issuer    = "https://clerk.example.com"
allowed_origins = ["http://localhost:3000"]
```

`infra/api/.gitignore`:

```
.terraform/
.terraform.lock.hcl
terraform.tfstate
terraform.tfstate.backup
*.tfvars
!terraform.tfvars.example
```

- [ ] **Step 2: Init the module**

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/api && terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=api/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
cd -
```

Expected: `Terraform has been successfully initialized!`.

- [ ] **Step 3: Commit**

```sh
git add infra/api/
git commit -m "infra(api): module skeleton (backend/data/variables/outputs/.gitignore)"
```

---

### Task 7.2: Lambda + IAM (`main.tf`)

**Files:**
- Create: `infra/api/main.tf`

- [ ] **Step 1: Create the resource file**

`infra/api/main.tf`:

```hcl
locals {
  function_name           = "news-api-${terraform.workspace}"
  ssm_prefix              = "/news-aggregator/${terraform.workspace}"
  lambda_artifacts_bucket = "news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}"
  remix_sfn_arn           = data.terraform_remote_state.scheduler.outputs.remix_state_machine_arn
}

resource "aws_iam_role" "lambda_exec" {
  name = local.function_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "runtime" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # SSM SecureString reads (cold-start hydrates env from /news-aggregator/<env>/*).
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = [
          "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}",
          "arn:aws:ssm:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "kms:Decrypt"
        Resource = "arn:aws:kms:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:alias/aws/ssm"
      },
      # Step Functions: ONLY start_execution on the exact remix state machine.
      # Deliberately NOT granting DescribeExecution / ListExecutions — the API
      # doesn't proxy execution status, the frontend re-fetches /v1/digests.
      # Deliberately NOT granting StartExecution on the cron pipeline — that
      # would be a denial-of-wallet vector.
      {
        Effect   = "Allow"
        Action   = "states:StartExecution"
        Resource = local.remix_sfn_arn
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda_exec.arn
  package_type     = "Zip"
  runtime          = "python3.12"
  handler          = "lambda_handler.handler"
  s3_bucket        = local.lambda_artifacts_bucket
  s3_key           = var.zip_s3_key
  source_code_hash = var.zip_sha256
  timeout          = var.timeout
  memory_size      = var.memory_size
  architectures    = ["x86_64"]

  environment {
    variables = {
      ENV                       = terraform.workspace
      LOG_LEVEL                 = "INFO"
      LOG_JSON                  = "true"
      SSM_PARAM_PREFIX          = local.ssm_prefix
      REMIX_STATE_MACHINE_ARN   = local.remix_sfn_arn
      CLERK_ISSUER              = var.clerk_issuer
      CLERK_JWKS_URL            = "${var.clerk_issuer}/.well-known/jwks.json"
      ALLOWED_ORIGINS           = join(",", var.allowed_origins)
      GIT_SHA                   = var.git_sha
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.runtime,
    aws_cloudwatch_log_group.api,
  ]

  tags = { Project = "news-aggregator", Module = "api" }
}
```

- [ ] **Step 2: Plan to verify**

```sh
cd infra/api && terraform plan \
  -var=zip_s3_key=placeholder.zip \
  -var=zip_sha256=AAAA \
  -var=git_sha=test \
  -var='clerk_issuer=https://test.clerk.dev'
cd -
```

Expected: plan shows ~5 resources to add (role + policy attachment + inline policy + log group + lambda); no errors. (`terraform plan` may complain about the actual zip not existing in S3 — that's fine, we're checking syntax only.)

- [ ] **Step 3: Commit**

```sh
git add infra/api/main.tf
git commit -m "infra(api): Lambda function + IAM (SSM read + states:StartExecution on remix only)"
```

---

### Task 7.3: API Gateway HTTP API + integration + alarm

**Files:**
- Create: `infra/api/apigateway.tf`

- [ ] **Step 1: Create the file**

`infra/api/apigateway.tf`:

```hcl
resource "aws_apigatewayv2_api" "api" {
  name          = "news-api-${terraform.workspace}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins  = var.allowed_origins
    allow_methods  = ["GET", "PUT", "POST", "OPTIONS"]
    allow_headers  = ["Authorization", "Content-Type"]
    expose_headers = []
    max_age        = 3600
  }

  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/news-api-${terraform.workspace}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      httpMethod     = "$context.httpMethod"
      path           = "$context.path"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      sourceIp       = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
    })
  }

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }

  tags = { Project = "news-aggregator", Module = "api" }
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 15000
}

resource "aws_apigatewayv2_route" "proxy" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_lambda_permission" "allow_api_gw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "news-api-${terraform.workspace}-5xx"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "≥5 5XX responses from news-api in 5 min"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiId = aws_apigatewayv2_api.api.id
    Stage = aws_apigatewayv2_stage.default.name
  }
}
```

- [ ] **Step 2: Plan to verify**

```sh
cd infra/api && terraform plan \
  -var=zip_s3_key=placeholder.zip \
  -var=zip_sha256=AAAA \
  -var=git_sha=test \
  -var='clerk_issuer=https://test.clerk.dev'
cd -
```

Expected: total ~10 resources (Lambda + IAM + log group from 7.2, plus API + stage + integration + route + permission + access log group + alarm here). No errors.

- [ ] **Step 3: Commit**

```sh
git add infra/api/apigateway.tf
git commit -m "infra(api): API Gateway HTTP API + integration + CORS + 5xx alarm"
```

---

## Phase 8 — Build + deploy

### Task 8.1: `package_docker.py` + `deploy.py`

**Files:**
- Create: `services/api/package_docker.py`
- Create: `services/api/deploy.py`

- [ ] **Step 1: Create `package_docker.py`**

Create `services/api/package_docker.py` (mirroring the scheduler's, with `agent` → `api` and `news_api`):

```python
"""Build a Lambda zip artifact for the API service.

Uses public.ecr.aws/lambda/python:3.12 as the build image so wheels are amd64
manylinux. Output: services/api/dist/news_api.zip.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(__file__).resolve().parent
DIST = AGENT_DIR / "dist"
PACKAGE_NAME = "news_api"


_DOCKERFILE = """
FROM public.ecr.aws/lambda/python:3.12 AS build

WORKDIR /work
RUN dnf install -y zip && dnf clean all

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/{agent}/ ./services/{agent}/

COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

RUN uv export --no-dev --no-emit-workspace --package {package} --frozen \\
        --format requirements-txt > /tmp/req.txt
RUN python -m pip install -r /tmp/req.txt --target /pkg --no-cache-dir
RUN cp -r packages/schemas/src/news_schemas /pkg/ \\
 && cp -r packages/config/src/news_config /pkg/ \\
 && cp -r packages/observability/src/news_observability /pkg/ \\
 && cp -r packages/db/src/news_db /pkg/ \\
 && cp -r services/{agent}/src/{package} /pkg/ \\
 && cp services/{agent}/lambda_handler.py /pkg/lambda_handler.py

WORKDIR /pkg
RUN zip -r9 /tmp/{package}.zip . -x '*.pyc' '__pycache__/*' 'tests/*' '*/tests/*' '*/tests/**'

FROM scratch AS export
COPY --from=build /tmp/{package}.zip /
"""


def main() -> int:
    if shutil.which("docker") is None:
        print("ERROR: docker not found", file=sys.stderr)
        return 2

    DIST.mkdir(parents=True, exist_ok=True)
    dockerfile = AGENT_DIR / ".package.Dockerfile"
    dockerfile.write_text(_DOCKERFILE.format(agent=AGENT_DIR.name, package=PACKAGE_NAME))

    cmd = [
        "docker", "build", "--platform=linux/amd64",
        "--target=export", "--output", f"type=local,dest={DIST}",
        "-f", str(dockerfile), str(REPO_ROOT),
    ]
    subprocess.run(cmd, check=True)
    print(f"built: {DIST / (PACKAGE_NAME + '.zip')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Create `deploy.py`**

Create `services/api/deploy.py`. **Path note:** `AGENT_DIR.parents[1]` is the repo root (the API lives at `services/api/`, one level under `services/`, exactly like the scheduler). Don't use `parents[2]`.

```python
"""Build, upload, and deploy the API Lambda.

Modes:
  build   — package_docker.py → S3 upload
  deploy  — build + terraform apply
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import boto3

AGENT_DIR = Path(__file__).resolve().parent
PACKAGE = "news_api"
# AGENT_DIR is .../services/api — already the directory.
# parents[0]=services, parents[1]=repo_root. Don't copy `parents[2]` from
# the agents' deploy.py (they live one level deeper at services/agents/<x>/).
TF_DIR = AGENT_DIR.parents[1] / "infra" / "api"


def _profile() -> str:
    return os.environ.get("AWS_PROFILE", "aiengineer")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=_profile())


def _account_id(s: boto3.Session) -> str:
    return s.client("sts").get_caller_identity()["Account"]  # type: ignore[no-any-return]


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _bucket(s: boto3.Session) -> str:
    return f"news-aggregator-lambda-artifacts-{_account_id(s)}"


def _zip_path() -> Path:
    return AGENT_DIR / "dist" / f"{PACKAGE}.zip"


def _build_zip() -> Path:
    subprocess.run(
        ["uv", "run", "python", str(AGENT_DIR / "package_docker.py")],
        check=True,
    )
    z = _zip_path()
    if not z.exists():
        raise RuntimeError(f"build did not produce {z}")
    return z


def _b64_sha256(path: Path) -> str:
    h = hashlib.sha256(path.read_bytes()).digest()
    return base64.b64encode(h).decode()


def _upload(s: boto3.Session, sha: str, zip_path: Path) -> str:
    key = f"api/{sha}.zip"
    s.client("s3").upload_file(str(zip_path), _bucket(s), key)
    print(f"uploaded s3://{_bucket(s)}/{key}")
    return key


def cmd_build() -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    _upload(s, sha, zip_path)
    print(f"sha256(zip) = {_b64_sha256(zip_path)}")
    return 0


def cmd_deploy(env: str) -> int:
    clerk_issuer = os.environ.get("CLERK_ISSUER")
    if not clerk_issuer:
        print("ERROR: CLERK_ISSUER must be set "
              "(e.g. export CLERK_ISSUER=https://clerk.example.com)", file=sys.stderr)
        return 2

    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    key = _upload(s, sha, zip_path)
    sha256 = _b64_sha256(zip_path)

    allowed_origins_csv = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
    allowed_origins_tf = "[" + ",".join(
        f'"{o.strip()}"' for o in allowed_origins_csv.split(",") if o.strip()
    ) + "]"

    tf_env = {**os.environ, "AWS_PROFILE": _profile()}
    try:
        subprocess.run(["terraform", "workspace", "select", env],
                       cwd=TF_DIR, check=True, env=tf_env)
    except subprocess.CalledProcessError:
        subprocess.run(["terraform", "workspace", "new", env],
                       cwd=TF_DIR, check=True, env=tf_env)

    subprocess.run(
        [
            "terraform", "apply", "-auto-approve",
            f"-var=zip_s3_key={key}",
            f"-var=zip_sha256={sha256}",
            f"-var=git_sha={sha}",
            f"-var=clerk_issuer={clerk_issuer}",
            f"-var=allowed_origins={allowed_origins_tf}",
        ],
        cwd=TF_DIR, check=True, env=tf_env,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["build", "deploy"], required=True)
    p.add_argument("--env", default="dev")
    args = p.parse_args()
    return cmd_build() if args.mode == "build" else cmd_deploy(args.env)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Commit**

```sh
git add services/api/package_docker.py services/api/deploy.py
git commit -m "build(api): package_docker.py + deploy.py (mirror scheduler pattern)"
```

---

### Task 8.2: SSM seed (clerk_secret_key) + first live deploy + smoke

**Files:** none (live AWS work).

- [ ] **Step 1: Seed `clerk_secret_key` into SSM**

```sh
aws ssm put-parameter \
  --name /news-aggregator/dev/clerk_secret_key \
  --value "<your-clerk-secret-key>" \
  --type SecureString \
  --overwrite \
  --profile aiengineer
```

Expected: `{"Version": ..., "Tier": "Standard"}`.

- [ ] **Step 2: Build and deploy**

```sh
export CLERK_ISSUER=https://<your-clerk-frontend-api>
export ALLOWED_ORIGINS=http://localhost:3000
make api-deploy
```

(`make api-deploy` lands in Task 9.1 — for this step, run the deploy script directly: `uv run python services/api/deploy.py --mode deploy --env dev`.)

Expected: terraform `Apply complete!` with `api_endpoint`, `function_arn`, `function_name`, `log_group_name` outputs.

- [ ] **Step 3: Smoke /healthz**

```sh
URL=$(cd infra/api && terraform output -raw api_endpoint)
curl -s "$URL/v1/healthz" | jq
```

Expected:

```json
{"status": "ok", "git_sha": "<commit-sha>"}
```

- [ ] **Step 4: Smoke /me with a real Clerk JWT**

Mint a JWT from the Clerk dashboard (Quickstart → JWT template), then:

```sh
URL=$(cd infra/api && terraform output -raw api_endpoint)
curl -s -H "Authorization: Bearer <real-clerk-jwt>" "$URL/v1/me" | jq
```

Expected: 200 with the caller's `UserOut` and `profile_completed_at: null`.

- [ ] **Step 5: Smoke PUT /me/profile + /digests + /remix**

(Manual checks against the deployed endpoint with a real JWT — these should round-trip the profile, list digests created earlier by #3's cron, and trigger a remix execution that completes within ~30s.)

- [ ] **Step 6: If any smoke check fails**

Capture the diagnosis + fix as a separate commit (e.g. `fix(api): patch CORS origin for prod frontend`), or surface to the human as **BLOCKED** per subagent-driven-development guidance, before continuing to Phase 9.

---

## Phase 9 — Documentation + tag

### Task 9.1: Makefile additions

**Files:**
- Modify: [Makefile](Makefile)

- [ ] **Step 1: Append the api block**

Open `Makefile` and append after the existing `# ---------- scheduler (#3) ----------` block:

```makefile
# ---------- api (#4) ----------

.PHONY: api-serve api-deploy-build api-deploy api-invoke api-test-me \
        api-logs api-logs-follow tag-api

api-serve:                  ## run FastAPI locally on :8000
	uv run python -m news_api serve

api-deploy-build:           ## build + s3 upload (api)
	uv run python services/api/deploy.py --mode build

api-deploy:                 ## build + terraform apply (api)
	uv run python services/api/deploy.py --mode deploy --env dev

api-invoke:                 ## smoke /healthz on the deployed endpoint
	@URL=$$(cd infra/api && terraform output -raw api_endpoint) && \
	  curl -s "$$URL/v1/healthz" | jq

api-test-me:                ## test GET /me with $JWT (BYO token: export JWT=...)
	@test -n "$(JWT)" || (echo "JWT required: export JWT=<clerk-jwt>" && exit 1)
	@URL=$$(cd infra/api && terraform output -raw api_endpoint) && \
	  curl -s -H "Authorization: Bearer $(JWT)" "$$URL/v1/me" | jq

api-logs:                   ## tail api Lambda logs  [SINCE=10m]
	aws logs tail /aws/lambda/news-api-dev --since $${SINCE:-10m} --profile aiengineer

api-logs-follow:            ## follow api Lambda logs in real time
	aws logs tail /aws/lambda/news-api-dev --follow --profile aiengineer

tag-api:                    ## tag sub-project #4
	git tag -f -a api-v0.5.0 -m "Sub-project #4 API + Auth"
	@echo "Push with: git push origin api-v0.5.0"
```

- [ ] **Step 2: Verify**

```sh
make help | grep -E "api-|tag-api" | head -10
make -n api-serve
```

Expected: targets listed; `make -n api-serve` prints `uv run python -m news_api serve`.

- [ ] **Step 3: Commit**

```sh
git add Makefile
git commit -m "build(make): add api-/tag-api targets (local + invoke + logs)"
```

---

### Task 9.2: `infra/README.md` — Sub-project #4 section

**Files:**
- Modify: [infra/README.md](infra/README.md)

- [ ] **Step 1: Append the section**

Append at the end of `infra/README.md`:

```markdown
## Sub-project #4 — API + Auth

A `news-api-dev` Lambda fronted by an API Gateway HTTP API exposing six
endpoints (`/v1/healthz`, `/v1/me`, `/v1/me/profile`, `/v1/digests`,
`/v1/digests/{id}`, `/v1/remix`). Validates Clerk JWTs in a FastAPI
dependency, lazy-creates user rows on first call, and triggers the
remix state machine (#3) for on-demand digest re-runs.

### One-time IAM extension

**None.** `NewsAggregatorComputeAccess` already grants
`AWSLambda_FullAccess`, `AmazonAPIGatewayAdministrator`, and
`AmazonS3FullAccess` — those cover everything `infra/api/` provisions.

### Per-module Terraform init

```sh
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/api
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=api/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
terraform workspace new dev   # or: terraform workspace select dev
```

### SSM secret seed

```sh
aws ssm put-parameter \
  --name /news-aggregator/dev/clerk_secret_key \
  --value "<your-clerk-secret-key>" \
  --type SecureString \
  --overwrite \
  --profile aiengineer
```

`clerk_publishable_key` is **not** stored in SSM — it's, by definition,
public, and lives in the Next.js frontend's env file (#5).

### Deploy

```sh
export CLERK_ISSUER=https://<your-clerk-frontend-api>
export ALLOWED_ORIGINS=http://localhost:3000
make api-deploy
```

First apply creates ~10 resources: Lambda + IAM role + 2 policy attachments
+ log group + HTTP API + stage + integration + route + Lambda permission +
access log group + 5xx alarm.

### Invoke + monitor

```sh
make api-invoke                          # smoke /v1/healthz
make api-test-me JWT=<real-clerk-jwt>    # GET /v1/me

make api-logs SINCE=10m                  # tail Lambda logs
make api-logs-follow

# Local dev (no AWS):
make api-serve
```

### Failure modes

- **`401 invalid token` in dev** — your `CLERK_ISSUER` env var points at
  a different Clerk instance than the one minting your JWT. Run
  `terraform output -raw function_arn` then
  `aws lambda get-function-configuration --function-name news-api-dev
  --query 'Environment.Variables' --profile aiengineer` to inspect the
  deployed config.
- **`401 missing bearer token` from the frontend** — CORS preflight
  passing but the actual fetch missing `Authorization` header (common
  in Next.js fetches that don't pass `credentials: "include"` plus the
  token). Check the network tab.
- **`AccessDenied` on remix `start_execution`** — the API role's IAM
  is scoped to the *exact* remix ARN read via
  `terraform_remote_state.scheduler`. If you re-applied the scheduler
  with a different workspace, the API's stored ARN may be stale —
  re-run `terraform apply` on the API module.
- **`RuntimeError: ... attached to a different loop`** — the
  `reset_engine()` call at the top of `handler()` was removed or
  bypassed. Re-add it (see #2/#3 anti-pattern).
- **CORS preflight 404s** — `var.allowed_origins` doesn't include the
  caller's origin. Update and re-apply.

### Roll back

To roll back the Lambda code:

```sh
cd infra/api
terraform apply \
  -var=zip_s3_key=api/<previous-sha>.zip \
  -var=zip_sha256=<previous-base64-sha256> \
  -var=git_sha=<previous-sha> \
  -var=clerk_issuer=https://<your-clerk-frontend-api>
```

To destroy the API module entirely (keeps the artefact bucket, the
scheduler, and all state):

```sh
cd infra/api
terraform destroy -var=zip_s3_key=anything -var=zip_sha256=anything \
  -var=git_sha=anything -var=clerk_issuer=https://placeholder.example.com
```
```

- [ ] **Step 2: Commit**

```sh
git add infra/README.md
git commit -m "docs(infra): add sub-project #4 API + Auth section"
```

---

### Task 9.3: `AGENTS.md` refresh

**Files:**
- Modify: [AGENTS.md](AGENTS.md)

- [ ] **Step 1: Flip status, add layout, add ops section, add anti-patterns**

Apply these edits (one per change):

**a)** In the sub-project decomposition table:

```markdown
| **3** | Scheduler + orchestration — ... | shipped — tag `scheduler-v0.4.0` |
| **4** | API + Auth — `news-api` Lambda + API Gateway HTTP API + Clerk JWT (FastAPI dep, lazy upsert), per-sub-project Terraform under `infra/api/` | shipped — tag `api-v0.5.0` |
| 5 | Frontend (Next.js + Clerk + S3/CloudFront) | not started |
```

**b)** Update the `services/api/` line in the repo layout block — today it reads `# Lambda — FastAPI + Clerk (#4)` (a placeholder). Replace with:

```markdown
│   └── api/                        # Lambda — FastAPI on Mangum + Clerk JWT + remix trigger (#4)
```

Add `infra/api/` to the infra block (after `infra/scheduler/`):

```markdown
│   ├── scheduler/                  # scheduler Lambda + 2 SFN state machines + EventBridge cron + alarms (#3)
│   ├── api/                        # FastAPI Lambda + API Gateway HTTP API + IAM (#4)
│   └── setup-iam.sh                # one-time NewsAggregator{Core,Compute}Access groups
```

**c)** Add a new "Sub-project #4 (API) — operational commands" section, immediately after the existing `### Sub-project #3 (Scheduler) — operational commands` section and before `## What NOT to do`:

```markdown
### Sub-project #4 (API) — operational commands

A `news-api-dev` Lambda behind an API Gateway HTTP API. FastAPI app
served via Mangum; Clerk JWT validated in a FastAPI dependency
(`get_current_user`); lazy-upserts users on first call; triggers the
remix state machine (#3) for on-demand digest re-runs.

```sh
# Local dev
make api-serve                                # uvicorn http://localhost:8000

# AWS deploy (requires CLERK_ISSUER in env)
export CLERK_ISSUER=https://<clerk-frontend-api>
make api-deploy

# Smoke
make api-invoke                               # /v1/healthz
make api-test-me JWT=<real-clerk-jwt>         # /v1/me

# Logs
make api-logs SINCE=10m
make api-logs-follow
```

The API reads SSM SecureStrings at cold-start (same `/news-aggregator/<env>/*`
tree as #1-#3). It additionally reads `CLERK_ISSUER` and the remix state
machine ARN as Lambda env vars (set by Terraform via
`terraform_remote_state.scheduler`) — neither is secret.

See `infra/README.md` § "Sub-project #4 — API + Auth" for full
lifecycle, IAM scope (deliberately narrow — only `states:StartExecution`
on the exact remix ARN), and rollback recipe.
```

**d)** Append to "What NOT to do":

```markdown
- Do not ship a `DEV_AUTH_BYPASS=1` flag on the API. The auth flow is well-trodden enough that minting a Clerk dashboard JWT for local curl is not real friction; bypass flags are a reliability liability (easy to leave on, easy to misconfigure in prod).
- Do not grant `states:DescribeExecution` or `states:ListExecutions` to the API Lambda's role. The frontend re-fetches `/v1/digests` to observe remix completion; proxying execution status would just be a latency tax and a wider IAM blast radius.
- Do not store `clerk_publishable_key` in SSM. It is, by definition, public — it lives in the Next.js frontend's env file (#5), never in the backend.
- Do not skip the algorithm whitelist when calling `pyjwt.decode`. Hard-coding `algorithms=["RS256"]` defeats the algorithm-confusion attack class (HS256 token forged with the public key as a shared secret).
- Do not call `boto3` directly from a route handler. Wrap it in `services/api/src/news_api/clients/<service>.py` so the dependency direction is `routes → clients → boto3`, and the only `import boto3` lives in one focused file.
- Do not validate JWTs at API Gateway via the `aws_apigatewayv2_authorizer` JWT integration. The lazy-upsert flow needs claims inside the handler anyway, so we'd validate twice; the FastAPI dep is the single source of truth.
```

- [ ] **Step 2: Commit**

```sh
git add AGENTS.md
git commit -m "docs(agents): refresh AGENTS.md for sub-project #4 (API + Auth)"
```

---

### Task 9.4: `README.md` refresh

**Files:**
- Modify: [README.md](README.md)

- [ ] **Step 1: Flip the status badges + status table to mark #4 shipped**

Edit the badges block at the top:

```markdown
[![API](https://img.shields.io/badge/sub--project%20%234-api--v0.5.0-success)](https://github.com/PatrickCmd/ai-agents-news-aggregator/releases/tag/api-v0.5.0)
```

Flip the row in the "Solution at a Glance" table:

```markdown
| **4** | **API + Auth** | FastAPI on Lambda + API Gateway HTTP API + Clerk JWT (lazy-upsert via FastAPI dep). Six endpoints powering the upcoming Next.js frontend (#5). | ✅ shipped |
```

Flip the row in "Project Status":

```markdown
| 4 | API + Auth | `api-v0.5.0` | ✅ Lambda + API Gateway HTTP API + IAM scoped to remix SFN |
```

- [ ] **Step 2: Add a "Running the API (#4)" section**

Insert after "Running the scheduler (#3)" and before "Day-to-day commands":

```markdown
## Running the API (#4)

A FastAPI app on Lambda behind API Gateway HTTP API, exposing six
endpoints (`/v1/healthz`, `/v1/me`, `/v1/me/profile`, `/v1/digests`,
`/v1/digests/{id}`, `/v1/remix`) for the upcoming Next.js frontend.
JWTs from Clerk are validated in a FastAPI dependency that
lazy-upserts the user row on first call.

```sh
# Local dev (uvicorn — bypasses Mangum)
make api-serve

# Deploy (CLERK_ISSUER required for first deploy)
export CLERK_ISSUER=https://<clerk-frontend-api>
make api-deploy

# Smoke
make api-invoke                            # GET /v1/healthz
make api-test-me JWT=<real-clerk-jwt>      # GET /v1/me

# Logs
make api-logs SINCE=10m
make api-logs-follow
```

Sub-project #4 adds one new SSM SecureString (`clerk_secret_key`); the
publishable key lives in the frontend, not the backend. See
[infra/README.md](infra/README.md) § "Sub-project #4 — API + Auth"
for full lifecycle, IAM scope, and failure modes.
```

- [ ] **Step 3: Commit**

```sh
git add README.md
git commit -m "docs(readme): refresh status + add Running the API (#4) section"
```

---

### Task 9.5: Final verify + tag

**Files:** none (verification + git tag).

- [ ] **Step 1: Run the full quality gate**

```sh
make check
```

Expected: lint ✅, typecheck ✅, all tests pass.

If any unit/integration test fails, fix it before tagging.

- [ ] **Step 2: Create the tag**

```sh
make tag-scheduler   # sanity — confirm tag-* style works
make tag-api
```

Expected: tag `api-v0.5.0` exists locally.

- [ ] **Step 3: Verify and announce next steps**

```sh
git tag --list "api-*" -n3
git log --oneline main..HEAD | head -25
```

Expected: branch ahead of main with all the commits from Phases 0-9, plus the `api-v0.5.0` tag.

To push: `git push origin api-v0.5.0` (after merging the branch to main).

---

## Final tasks (after all phases complete)

- [ ] **Run the full integration suite end-to-end against the deployed Lambda**

```sh
make api-test-me JWT=<real-clerk-jwt>
URL=$(cd infra/api && terraform output -raw api_endpoint)
curl -s -X PUT "$URL/v1/me/profile" \
  -H "Authorization: Bearer <real-clerk-jwt>" \
  -H "Content-Type: application/json" \
  -d @config/user_profile.yml-as-json | jq
curl -s "$URL/v1/digests?limit=5" -H "Authorization: Bearer <real-clerk-jwt>" | jq
curl -s -X POST "$URL/v1/remix" \
  -H "Authorization: Bearer <real-clerk-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"lookback_hours":24}' | jq
```

Expected: each call returns its documented status code and shape.

- [ ] **Verify CloudWatch alarm wires up**

```sh
aws cloudwatch describe-alarms \
  --alarm-names news-api-dev-5xx \
  --profile aiengineer \
  --query 'MetricAlarms[].{State:StateValue,Threshold:Threshold,Metric:MetricName}'
```

Expected: alarm exists, `OK` or `INSUFFICIENT_DATA` state.

- [ ] **Confirm `CLAUDE.md` has no stale references that need updating** (grep for `#4`, `api`, `Clerk` mentions). Update if the project's working notes mention #4 as "not started" anywhere.

---

## Self-review notes (for the implementer)

Pre-completion sanity check:

1. **Spec coverage** — every section of `docs/superpowers/specs/2026-04-27-api-design.md` has a concrete task in this plan: §1 goal/non-goals (whole plan), §2 architecture (Phases 4-6), §3 auth (Phase 3 + Task 4.2), §4 endpoints (Tasks 4.1, 4.3, 4.4, 4.5, 5.2), §5 remix internals (Phase 5 + Task 7.2 IAM), §6 infra (Phase 7), §7 local dev + Makefile (Tasks 6.2, 9.1), §8 testing (every Task that creates code has its TDD shape), §9 glossary (every glossary item is created in a numbered task), §10 risks (mitigations are wired into the relevant tasks).

2. **Type consistency** — `UserProfile.empty()` (Task 0.1) is referenced by `get_current_user` (Task 4.2). `DigestSummaryOut` (Task 0.2) is referenced by `DigestRepository.get_for_user` (Task 1.1) and the digests routes (Task 4.5). `AgentName.API` and the two new `DecisionType` values (Task 0.3) are referenced by the route handlers (Tasks 4.4 and 5.2). `start_remix` signature is consistent across the wrapper (Task 5.1), the route (Task 5.2), and the test mock.

3. **No placeholders** — every step contains either complete code, an exact command, or a copy-pastable patch. No "TBD", no "implement later", no "add appropriate error handling".

4. **Frequent commits** — every task ends with a focused conventional-commit; the plan totals ~25 commits, mirroring the cadence of #2 and #3.
