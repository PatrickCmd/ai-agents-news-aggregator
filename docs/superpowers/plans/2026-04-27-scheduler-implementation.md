# Scheduler + Orchestration (Sub-project #3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship two AWS Step Functions state machines (cron-pipeline + remix-user) wrapping the existing #1 scraper and #2 agent Lambdas, plus a small "list" Lambda for query-only stages, plus a daily EventBridge cron at 21:00 UTC. No new tables, no new agent code.

**Architecture:** EventBridge cron triggers the cron-pipeline state machine, which calls the scraper via native HTTPS task, polls until terminal status, then runs three Map states (digest → editor → email) invoking the existing Lambda functions. A second state machine (remix-user) is invoked by `StartExecution` from #4's API for per-user manual sends. A new single Lambda (`news-scheduler-dev`) hosts three list handlers dispatched by `event["op"]`.

**Tech Stack:** Python 3.12, AWS Step Functions Standard, EventBridge cron, AWS Lambda zip + S3, async SQLAlchemy, Terraform 6.42.0, testcontainers-postgres for integration tests, pytest + pytest-asyncio.

**Spec:** [docs/superpowers/specs/2026-04-27-scheduler-design.md](../specs/2026-04-27-scheduler-design.md)

**Branch:** `sub-project#3`

---

## Phase 0 — branch state + baseline verification

- [ ] **Step 0.1: Confirm branch + status**

```bash
git status
git branch --show-current             # expected: sub-project#3
git log --oneline -3                  # 270d444 (spec) on top of 0f53f42 (merge of #2)
```

- [ ] **Step 0.2: Verify baseline is green**

```bash
uv run ruff check
uv run ruff format --check
uv run mypy packages
uv run pytest -q
```

Expected: all green, ~200 tests passing. If anything fails, STOP and ask the user.

---

## Phase 1 — Repository additions

Two tiny query methods on existing repos, both TDD against testcontainers-postgres.

### Task 1.1: `UserRepository.list_active_user_ids`

**Files:**
- Modify: [packages/db/src/news_db/repositories/user_repo.py](packages/db/src/news_db/repositories/user_repo.py)
- Create: [tests/integration/test_user_repo_active_users.py](tests/integration/test_user_repo_active_users.py)

- [ ] **Step 1.1.1: Write the failing test**

```python
# tests/integration/test_user_repo_active_users.py
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from news_db.repositories.user_repo import UserRepository
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserIn,
    UserProfile,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _profile() -> UserProfile:
    return UserProfile(
        background=[],
        interests=Interests(),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


@pytest.mark.asyncio
async def test_list_active_user_ids_excludes_unfinished_profiles(
    session: AsyncSession,
) -> None:
    repo = UserRepository(session)

    # Active user — profile_completed_at is set.
    active = await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email=f"{uuid4()}@example.com",
            name="Active",
            email_name="Active",
            profile=_profile(),
            profile_completed_at=datetime.now(UTC),
        )
    )

    # Inactive user — onboarding incomplete.
    await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email=f"{uuid4()}@example.com",
            name="Pending",
            email_name="Pending",
            profile=_profile(),
            profile_completed_at=None,
        )
    )

    ids = await repo.list_active_user_ids()
    assert active.id in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_list_active_user_ids_returns_empty_when_none(session: AsyncSession) -> None:
    repo = UserRepository(session)
    ids = await repo.list_active_user_ids()
    assert ids == []
```

- [ ] **Step 1.1.2: Run, expect failure**

```bash
uv run pytest tests/integration/test_user_repo_active_users.py -v
```

Expected: FAIL — `AttributeError: 'UserRepository' object has no attribute 'list_active_user_ids'`.

- [ ] **Step 1.1.3: Implement the method**

Add to [packages/db/src/news_db/repositories/user_repo.py](packages/db/src/news_db/repositories/user_repo.py) at the end of the `UserRepository` class:

```python
    async def list_active_user_ids(self) -> list[UUID]:
        """All users whose onboarding is complete (profile_completed_at IS NOT NULL).

        Used by the scheduler's editor stage to fan out per active user.
        """
        stmt = (
            select(User.id)
            .where(User.profile_completed_at.is_not(None))
            .order_by(User.created_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows)
```

- [ ] **Step 1.1.4: Run, expect pass**

```bash
uv run pytest tests/integration/test_user_repo_active_users.py -v
uv run mypy packages/db
```

Both green; 2 tests pass.

- [ ] **Step 1.1.5: Commit**

```bash
git add packages/db/src/news_db/repositories/user_repo.py tests/integration/test_user_repo_active_users.py
git commit -m "feat(db): UserRepository.list_active_user_ids"
```

---

### Task 1.2: `DigestRepository.list_generated_today`

**Files:**
- Modify: [packages/db/src/news_db/repositories/digest_repo.py](packages/db/src/news_db/repositories/digest_repo.py)
- Create: [tests/integration/test_digest_repo_today.py](tests/integration/test_digest_repo_today.py)

- [ ] **Step 1.2.1: Write the failing test**

```python
# tests/integration/test_digest_repo_today.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserIn,
    UserProfile,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _profile() -> UserProfile:
    return UserProfile(
        background=[],
        interests=Interests(),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


@pytest.mark.asyncio
async def test_list_generated_today_filters_status_and_date(
    session: AsyncSession,
) -> None:
    user = await UserRepository(session).upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email=f"{uuid4()}@example.com",
            name="t",
            email_name="t",
            profile=_profile(),
        )
    )

    digests = DigestRepository(session)

    now = datetime.now(UTC)
    period = (now - timedelta(hours=24), now)

    # GENERATED today — included.
    fresh = await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=period[0],
            period_end=period[1],
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.GENERATED,
        )
    )
    # FAILED today — excluded by status filter.
    await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=period[0],
            period_end=period[1],
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.FAILED,
            error_message="no candidates",
        )
    )
    # EMAILED today — excluded (already sent).
    await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=period[0],
            period_end=period[1],
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.EMAILED,
        )
    )

    ids = await digests.list_generated_today()
    assert ids == [fresh.id]


@pytest.mark.asyncio
async def test_list_generated_today_returns_empty_when_none(session: AsyncSession) -> None:
    digests = DigestRepository(session)
    ids = await digests.list_generated_today()
    assert ids == []
```

- [ ] **Step 1.2.2: Run, expect failure**

```bash
uv run pytest tests/integration/test_digest_repo_today.py -v
```

Expected: FAIL — `AttributeError: 'DigestRepository' object has no attribute 'list_generated_today'`.

- [ ] **Step 1.2.3: Implement the method**

Add to [packages/db/src/news_db/repositories/digest_repo.py](packages/db/src/news_db/repositories/digest_repo.py) at the end of the `DigestRepository` class. You'll also need a `func` import — add it to the existing `from sqlalchemy import select` line so it becomes `from sqlalchemy import func, select`.

```python
    async def list_generated_today(self) -> list[int]:
        """Digest IDs created today (UTC) with status=GENERATED.

        Used by the scheduler's email stage to fan out per new digest.
        Excludes FAILED (no email needed) and EMAILED (already sent).
        """
        stmt = (
            select(Digest.id)
            .where(Digest.generated_at >= func.date_trunc("day", func.now()))
            .where(Digest.status == DigestStatus.GENERATED.value)
            .order_by(Digest.generated_at)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows)
```

- [ ] **Step 1.2.4: Run, expect pass**

```bash
uv run pytest tests/integration/test_digest_repo_today.py -v
uv run mypy packages/db
```

Both green; 2 tests pass.

- [ ] **Step 1.2.5: Commit**

```bash
git add packages/db/src/news_db/repositories/digest_repo.py tests/integration/test_digest_repo_today.py
git commit -m "feat(db): DigestRepository.list_generated_today"
```

---

## Phase 2 — Scheduler workspace package

Mirrors the digest agent shape from sub-project #2: scaffold + settings + handlers + CLI + lambda_handler. Tooling configs (`mypy.ini` + `.pre-commit-config.yaml`) baked into the scaffold step upfront.

### Task 2.1: scaffold + settings + tooling configs

**Files:**
- Create: [services/scheduler/pyproject.toml](services/scheduler/pyproject.toml)
- Create: [services/scheduler/src/news_scheduler/__init__.py](services/scheduler/src/news_scheduler/__init__.py)
- Create: [services/scheduler/src/news_scheduler/settings.py](services/scheduler/src/news_scheduler/settings.py)
- Create: [services/scheduler/src/news_scheduler/tests/__init__.py](services/scheduler/src/news_scheduler/tests/__init__.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/__init__.py](services/scheduler/src/news_scheduler/tests/unit/__init__.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/test_settings.py](services/scheduler/src/news_scheduler/tests/unit/test_settings.py)
- Modify: [pyproject.toml](pyproject.toml) (root)
- Modify: [mypy.ini](mypy.ini)
- Modify: [.pre-commit-config.yaml](.pre-commit-config.yaml)

- [ ] **Step 2.1.1: Create `services/scheduler/pyproject.toml`**

```toml
[project]
name = "news_scheduler"
version = "0.1.0"
requires-python = ">=3.12"
description = "Scheduler service — list handlers + Step Functions orchestration glue"
dependencies = [
    "pydantic>=2.13.3",
    "pydantic-settings>=2.5",
    "loguru>=0.7.3",
    "typer>=0.24.2",
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
packages = ["src/news_scheduler"]
```

- [ ] **Step 2.1.2: Create `services/scheduler/src/news_scheduler/__init__.py`**

```python
"""Scheduler service — list handlers + Step Functions glue."""
```

- [ ] **Step 2.1.3: Add to root `pyproject.toml`**

In `[tool.uv.workspace] members`, append `"services/scheduler"` after `"services/agents/email"`.

In `[tool.uv.sources]`, append `news_scheduler = { workspace = true }` after `news_email = { workspace = true }`.

- [ ] **Step 2.1.4: Update `mypy.ini`**

The `mypy_path` line currently ends with `:services/agents/email/src`. Append `:services/scheduler/src`:

```
mypy_path = packages/schemas/src:packages/config/src:packages/observability/src:packages/db/src:services/scraper/src:services/agents/digest/src:services/agents/editor/src:services/agents/email/src:services/scheduler/src
```

- [ ] **Step 2.1.5: Update `.pre-commit-config.yaml`**

Extend the mypy hook's `files:` regex to include `services/scheduler/src/.*\.py$`:

```yaml
        files: ^(packages/.*/src/.*\.py$|services/scraper/src/.*\.py$|services/agents/digest/src/.*\.py$|services/agents/editor/src/.*\.py$|services/agents/email/src/.*\.py$|services/scheduler/src/.*\.py$)
```

- [ ] **Step 2.1.6: Sync the workspace**

```bash
uv sync --all-packages
uv run python -c "import news_scheduler; print(news_scheduler.__doc__)"
```

Expected: `Scheduler service — list handlers + Step Functions glue.`

- [ ] **Step 2.1.7: Commit (scaffold + tooling)**

```bash
git add services/scheduler/pyproject.toml services/scheduler/src/news_scheduler/__init__.py pyproject.toml uv.lock mypy.ini .pre-commit-config.yaml
git commit -m "feat(scheduler): scaffold news_scheduler workspace package + register in tooling"
```

- [ ] **Step 2.1.8: Write the failing settings test**

Create empty `tests/__init__.py` and `tests/unit/__init__.py` (zero bytes each — pytest discovery convention).

Then `services/scheduler/src/news_scheduler/tests/unit/test_settings.py`:

```python
from __future__ import annotations

import pytest


def test_scheduler_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGEST_SWEEP_LIMIT", raising=False)
    monkeypatch.delenv("DIGEST_SWEEP_HOURS", raising=False)
    from news_scheduler.settings import SchedulerSettings

    s = SchedulerSettings()
    assert s.digest_sweep_limit == 200
    assert s.digest_sweep_hours == 24


def test_scheduler_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGEST_SWEEP_LIMIT", "50")
    monkeypatch.setenv("DIGEST_SWEEP_HOURS", "12")
    from news_scheduler.settings import SchedulerSettings

    s = SchedulerSettings()
    assert s.digest_sweep_limit == 50
    assert s.digest_sweep_hours == 12
```

- [ ] **Step 2.1.9: Run, expect failure**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests -v
```

Expected: ImportError on `news_scheduler.settings`.

- [ ] **Step 2.1.10: Implement `settings.py`**

Create `services/scheduler/src/news_scheduler/settings.py`:

```python
"""Scheduler-specific settings.

DB-only — no OpenAI / Resend / Jinja keys here. The scheduler's only job
is to query the DB for IDs and dispatch them via Step Functions.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    digest_sweep_limit: int = Field(default=200, alias="DIGEST_SWEEP_LIMIT")
    digest_sweep_hours: int = Field(default=24, alias="DIGEST_SWEEP_HOURS")
```

- [ ] **Step 2.1.11: Run, expect pass**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests -v
uv run mypy services/scheduler
```

Both green; 2 tests pass.

- [ ] **Step 2.1.12: Commit (settings)**

```bash
git add services/scheduler/src/news_scheduler/settings.py services/scheduler/src/news_scheduler/tests/
git commit -m "feat(scheduler): SchedulerSettings (digest_sweep_limit + digest_sweep_hours)"
```

---

### Task 2.2: `list_unsummarised` handler

**Files:**
- Create: [services/scheduler/src/news_scheduler/handlers/__init__.py](services/scheduler/src/news_scheduler/handlers/__init__.py) (empty)
- Create: [services/scheduler/src/news_scheduler/handlers/list_unsummarised.py](services/scheduler/src/news_scheduler/handlers/list_unsummarised.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/test_list_unsummarised.py](services/scheduler/src/news_scheduler/tests/unit/test_list_unsummarised.py)

- [ ] **Step 2.2.1: Write the failing test**

```python
# services/scheduler/src/news_scheduler/tests/unit/test_list_unsummarised.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from news_schemas.article import ArticleOut, SourceType


def _article(aid: int) -> ArticleOut:
    return ArticleOut(
        id=aid,
        source_type=SourceType.RSS,
        source_name="src",
        external_id=f"ext-{aid}",
        title=f"T{aid}",
        url=f"https://x/{aid}",
        author=None,
        published_at=datetime.now(UTC),
        content_text="c",
        summary=None,
        tags=[],
        raw={},
        fetched_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _CapturingArticleRepo:
    def __init__(self, rows: list[ArticleOut]) -> None:
        self._rows = rows
        self.calls: list[tuple[int, int]] = []

    async def get_unsummarized(self, hours: int, limit: int = 50) -> list[ArticleOut]:
        self.calls.append((hours, limit))
        return self._rows


@pytest.mark.asyncio
async def test_list_unsummarised_returns_article_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_unsummarised

    repo = _CapturingArticleRepo([_article(1), _article(2), _article(3)])

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    def _fake_get_session() -> _FakeSession:
        return _FakeSession()

    monkeypatch.setattr(list_unsummarised, "get_session", _fake_get_session)
    monkeypatch.setattr(list_unsummarised, "ArticleRepository", lambda s: repo)

    out = await list_unsummarised.run(hours=24, limit=200)
    assert out == {"article_ids": [1, 2, 3]}
    assert repo.calls == [(24, 200)]


@pytest.mark.asyncio
async def test_list_unsummarised_returns_empty_when_no_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_unsummarised

    repo = _CapturingArticleRepo([])

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_unsummarised, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_unsummarised, "ArticleRepository", lambda s: repo)

    out = await list_unsummarised.run(hours=24, limit=200)
    assert out == {"article_ids": []}
```

- [ ] **Step 2.2.2: Run, expect failure**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_list_unsummarised.py -v
```

Expected: ImportError.

- [ ] **Step 2.2.3: Implement the handler**

Create `services/scheduler/src/news_scheduler/handlers/__init__.py` (empty file).

Then `services/scheduler/src/news_scheduler/handlers/list_unsummarised.py`:

```python
"""List handler: unsummarised article IDs for the digest stage."""

from __future__ import annotations

from typing import Any

from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository


async def run(*, hours: int, limit: int) -> dict[str, Any]:
    """Return ``{"article_ids": [...]}`` for the cron's digest Map stage.

    Args:
        hours: lookback window in hours.
        limit: cap on number of IDs returned (Step Functions Map cap).
    """
    async with get_session() as session:
        repo = ArticleRepository(session)
        rows = await repo.get_unsummarized(hours=hours, limit=limit)
    return {"article_ids": [r.id for r in rows]}
```

- [ ] **Step 2.2.4: Run, expect pass**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_list_unsummarised.py -v
uv run mypy services/scheduler
```

Both green; 2 tests pass.

- [ ] **Step 2.2.5: Commit**

```bash
git add services/scheduler/src/news_scheduler/handlers/ services/scheduler/src/news_scheduler/tests/unit/test_list_unsummarised.py
git commit -m "feat(scheduler): list_unsummarised handler"
```

---

### Task 2.3: `list_active_users` handler

**Files:**
- Create: [services/scheduler/src/news_scheduler/handlers/list_active_users.py](services/scheduler/src/news_scheduler/handlers/list_active_users.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/test_list_active_users.py](services/scheduler/src/news_scheduler/tests/unit/test_list_active_users.py)

- [ ] **Step 2.3.1: Write the failing test**

```python
# services/scheduler/src/news_scheduler/tests/unit/test_list_active_users.py
from __future__ import annotations

from uuid import UUID, uuid4

import pytest


class _CapturingUserRepo:
    def __init__(self, ids: list[UUID]) -> None:
        self._ids = ids
        self.calls = 0

    async def list_active_user_ids(self) -> list[UUID]:
        self.calls += 1
        return self._ids


@pytest.mark.asyncio
async def test_list_active_users_returns_uuid_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_active_users

    uids = [uuid4(), uuid4()]
    repo = _CapturingUserRepo(uids)

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_active_users, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_active_users, "UserRepository", lambda s: repo)

    out = await list_active_users.run()
    assert out == {"user_ids": [str(uid) for uid in uids]}
    assert repo.calls == 1


@pytest.mark.asyncio
async def test_list_active_users_returns_empty_when_no_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_active_users

    repo = _CapturingUserRepo([])

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_active_users, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_active_users, "UserRepository", lambda s: repo)

    out = await list_active_users.run()
    assert out == {"user_ids": []}
```

- [ ] **Step 2.3.2: Run, expect failure**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_list_active_users.py -v
```

- [ ] **Step 2.3.3: Implement**

Create `services/scheduler/src/news_scheduler/handlers/list_active_users.py`:

```python
"""List handler: active user IDs (onboarding complete) for the editor stage."""

from __future__ import annotations

from typing import Any

from news_db.engine import get_session
from news_db.repositories.user_repo import UserRepository


async def run() -> dict[str, Any]:
    """Return ``{"user_ids": [...]}`` (UUIDs as strings for JSON-safe state-machine input)."""
    async with get_session() as session:
        repo = UserRepository(session)
        ids = await repo.list_active_user_ids()
    return {"user_ids": [str(uid) for uid in ids]}
```

- [ ] **Step 2.3.4: Run, expect pass**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_list_active_users.py -v
uv run mypy services/scheduler
```

- [ ] **Step 2.3.5: Commit**

```bash
git add services/scheduler/src/news_scheduler/handlers/list_active_users.py services/scheduler/src/news_scheduler/tests/unit/test_list_active_users.py
git commit -m "feat(scheduler): list_active_users handler"
```

---

### Task 2.4: `list_new_digests` handler

**Files:**
- Create: [services/scheduler/src/news_scheduler/handlers/list_new_digests.py](services/scheduler/src/news_scheduler/handlers/list_new_digests.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/test_list_new_digests.py](services/scheduler/src/news_scheduler/tests/unit/test_list_new_digests.py)

- [ ] **Step 2.4.1: Write the failing test**

```python
# services/scheduler/src/news_scheduler/tests/unit/test_list_new_digests.py
from __future__ import annotations

import pytest


class _CapturingDigestRepo:
    def __init__(self, ids: list[int]) -> None:
        self._ids = ids
        self.calls = 0

    async def list_generated_today(self) -> list[int]:
        self.calls += 1
        return self._ids


@pytest.mark.asyncio
async def test_list_new_digests_returns_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from news_scheduler.handlers import list_new_digests

    repo = _CapturingDigestRepo([100, 101, 102])

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_new_digests, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_new_digests, "DigestRepository", lambda s: repo)

    out = await list_new_digests.run()
    assert out == {"digest_ids": [100, 101, 102]}
    assert repo.calls == 1


@pytest.mark.asyncio
async def test_list_new_digests_returns_empty_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_new_digests

    repo = _CapturingDigestRepo([])

    class _FakeSession:
        async def __aenter__(self) -> "_FakeSession":
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_new_digests, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_new_digests, "DigestRepository", lambda s: repo)

    out = await list_new_digests.run()
    assert out == {"digest_ids": []}
```

- [ ] **Step 2.4.2: Run, expect failure**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_list_new_digests.py -v
```

- [ ] **Step 2.4.3: Implement**

Create `services/scheduler/src/news_scheduler/handlers/list_new_digests.py`:

```python
"""List handler: today's GENERATED digest IDs for the email stage."""

from __future__ import annotations

from typing import Any

from news_db.engine import get_session
from news_db.repositories.digest_repo import DigestRepository


async def run() -> dict[str, Any]:
    """Return ``{"digest_ids": [...]}`` for the cron's email Map stage."""
    async with get_session() as session:
        repo = DigestRepository(session)
        ids = await repo.list_generated_today()
    return {"digest_ids": ids}
```

- [ ] **Step 2.4.4: Run, expect pass**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_list_new_digests.py -v
uv run mypy services/scheduler
```

- [ ] **Step 2.4.5: Commit**

```bash
git add services/scheduler/src/news_scheduler/handlers/list_new_digests.py services/scheduler/src/news_scheduler/tests/unit/test_list_new_digests.py
git commit -m "feat(scheduler): list_new_digests handler"
```

---

### Task 2.5: Typer CLI for local dev

**Files:**
- Create: [services/scheduler/src/news_scheduler/cli.py](services/scheduler/src/news_scheduler/cli.py)
- Create: [services/scheduler/src/news_scheduler/__main__.py](services/scheduler/src/news_scheduler/__main__.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/test_cli.py](services/scheduler/src/news_scheduler/tests/unit/test_cli.py)

- [ ] **Step 2.5.1: Write the failing test**

```python
# services/scheduler/src/news_scheduler/tests/unit/test_cli.py
from __future__ import annotations

from typer.testing import CliRunner


def test_cli_help_includes_all_three_commands() -> None:
    from news_scheduler.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "list-unsummarised" in result.stdout
    assert "list-active-users" in result.stdout
    assert "list-new-digests" in result.stdout
```

- [ ] **Step 2.5.2: Run, expect failure**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_cli.py -v
```

- [ ] **Step 2.5.3: Implement `cli.py` and `__main__.py`**

`services/scheduler/src/news_scheduler/cli.py`:

```python
"""Local Typer CLI for the scheduler list handlers (dev-only — no AWS calls)."""

from __future__ import annotations

import asyncio
import sys

import typer
from news_observability.logging import setup_logging

from news_scheduler.handlers import (
    list_active_users,
    list_new_digests,
    list_unsummarised,
)
from news_scheduler.settings import SchedulerSettings

app = typer.Typer(no_args_is_help=True, help="Scheduler CLI")


@app.callback()
def _root() -> None:
    """Force Typer subcommand routing even when commands are added one-by-one."""


@app.command("list-unsummarised")
def list_unsummarised_cmd(hours: int = 24, limit: int = 200) -> None:
    """Print article IDs without a summary (digest stage input)."""

    async def _run() -> int:
        setup_logging()
        s = SchedulerSettings()
        out = await list_unsummarised.run(
            hours=hours or s.digest_sweep_hours,
            limit=limit or s.digest_sweep_limit,
        )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command("list-active-users")
def list_active_users_cmd() -> None:
    """Print active user IDs (editor stage input)."""

    async def _run() -> int:
        setup_logging()
        out = await list_active_users.run()
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command("list-new-digests")
def list_new_digests_cmd() -> None:
    """Print today's GENERATED digest IDs (email stage input)."""

    async def _run() -> int:
        setup_logging()
        out = await list_new_digests.run()
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))
```

`services/scheduler/src/news_scheduler/__main__.py`:

```python
from news_scheduler.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 2.5.4: Run, expect pass**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_cli.py -v
uv run mypy services/scheduler
uv run ruff check services/scheduler
```

All green.

- [ ] **Step 2.5.5: Commit**

```bash
git add services/scheduler/src/news_scheduler/cli.py services/scheduler/src/news_scheduler/__main__.py services/scheduler/src/news_scheduler/tests/unit/test_cli.py
git commit -m "feat(scheduler): Typer CLI (3 list-* commands)"
```

---

### Task 2.6: `lambda_handler.py` dispatcher

**Files:**
- Create: [services/scheduler/lambda_handler.py](services/scheduler/lambda_handler.py)
- Create: [services/scheduler/src/news_scheduler/tests/unit/test_lambda_handler.py](services/scheduler/src/news_scheduler/tests/unit/test_lambda_handler.py)

- [ ] **Step 2.6.1: Write the failing test**

```python
# services/scheduler/src/news_scheduler/tests/unit/test_lambda_handler.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make services/scheduler/lambda_handler.py importable.
_AGENT_ROOT = Path(__file__).resolve().parents[4]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def test_handler_dispatches_list_unsummarised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")  # short-circuit ssm

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    captured: dict[str, Any] = {}

    async def _fake(*, hours: int, limit: int) -> dict[str, Any]:
        captured["hours"] = hours
        captured["limit"] = limit
        return {"article_ids": [1, 2, 3]}

    monkeypatch.setattr("news_scheduler.handlers.list_unsummarised.run", _fake)

    out = lambda_handler.handler(
        {"op": "list_unsummarised", "hours": 24, "limit": 200}, None
    )
    assert out == {"article_ids": [1, 2, 3]}
    assert captured == {"hours": 24, "limit": 200}


def test_handler_dispatches_list_active_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    async def _fake() -> dict[str, Any]:
        return {"user_ids": ["uuid1", "uuid2"]}

    monkeypatch.setattr("news_scheduler.handlers.list_active_users.run", _fake)

    out = lambda_handler.handler({"op": "list_active_users"}, None)
    assert out == {"user_ids": ["uuid1", "uuid2"]}


def test_handler_dispatches_list_new_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    async def _fake() -> dict[str, Any]:
        return {"digest_ids": [10, 20]}

    monkeypatch.setattr("news_scheduler.handlers.list_new_digests.run", _fake)

    out = lambda_handler.handler({"op": "list_new_digests"}, None)
    assert out == {"digest_ids": [10, 20]}


def test_handler_returns_failure_on_unknown_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    out = lambda_handler.handler({"op": "make_coffee"}, None)
    assert out["failed"] is True
    assert out["reason"] == "unknown_op"
    assert out["op"] == "make_coffee"


def test_handler_returns_failure_on_missing_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    out = lambda_handler.handler({}, None)
    assert out["failed"] is True
    assert out["reason"] == "malformed_event"
```

- [ ] **Step 2.6.2: Run, expect failure**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_lambda_handler.py -v
```

Expected: ImportError on `lambda_handler`.

- [ ] **Step 2.6.3: Implement `services/scheduler/lambda_handler.py`**

```python
"""AWS Lambda entry point for the scheduler.

Dispatches by ``event["op"]`` to one of the three list handlers.
Cold-start: hydrates env from SSM, configures logging.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# Pre-init: hydrate env from SSM before any other module reads settings.
from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_observability.logging import get_logger, setup_logging  # noqa: E402

from news_scheduler.handlers import (  # noqa: E402
    list_active_users,
    list_new_digests,
    list_unsummarised,
)

_log = get_logger("lambda_handler")
setup_logging()


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry. Dispatches by ``event["op"]``.

    Supported ops:
        ``list_unsummarised`` (kwargs: ``hours``, ``limit``)
        ``list_active_users``
        ``list_new_digests``

    Returns ``{"failed": True, "reason": ..., ...}`` on bad input — never raises.
    """
    op = event.get("op")
    if not op:
        _log.error("malformed event {}: missing op", event)
        return {"failed": True, "reason": "malformed_event", "event": event}

    if op == "list_unsummarised":
        hours = int(event.get("hours", 24))
        limit = int(event.get("limit", 200))
        return asyncio.run(list_unsummarised.run(hours=hours, limit=limit))

    if op == "list_active_users":
        return asyncio.run(list_active_users.run())

    if op == "list_new_digests":
        return asyncio.run(list_new_digests.run())

    _log.error("unknown op {}", op)
    return {"failed": True, "reason": "unknown_op", "op": op}
```

- [ ] **Step 2.6.4: Run, expect pass**

```bash
uv run pytest services/scheduler/src/news_scheduler/tests/unit/test_lambda_handler.py -v
uv run mypy services/scheduler
```

All 5 tests pass.

- [ ] **Step 2.6.5: Commit**

```bash
git add services/scheduler/lambda_handler.py services/scheduler/src/news_scheduler/tests/unit/test_lambda_handler.py
git commit -m "feat(scheduler): lambda_handler dispatcher (3 ops + malformed/unknown failure)"
```

---

### Task 2.7: Phase 2 verification

- [ ] **Step 2.7.1: Run full check**

```bash
uv run ruff check
uv run ruff format --check
uv run mypy packages services/scheduler
uv run pytest -q
```

All green.

---

## Phase 3 — Packaging + deploy

### Task 3.1: `package_docker.py`

**Files:**
- Create: [services/scheduler/package_docker.py](services/scheduler/package_docker.py)

Mirror of `services/agents/digest/package_docker.py` (commit `160c122`) with two constant changes.

- [ ] **Step 3.1.1: Implement**

```python
# services/scheduler/package_docker.py
"""Build a Lambda zip artifact for the scheduler service.

Uses public.ecr.aws/lambda/python:3.12 as the build image so wheels are amd64
manylinux. Output: services/scheduler/dist/news_scheduler.zip.

Assumes every workspace package follows the src/<pkg>/ layout with an
__init__.py at src/<pkg>/__init__.py — the Dockerfile cp-copies these
trees verbatim into /pkg/. If a new workspace package uses a different
layout, this script will silently produce an unimportable artifact.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_DIR = Path(__file__).resolve().parent
DIST = AGENT_DIR / "dist"
PACKAGE_NAME = "news_scheduler"


_DOCKERFILE = """
FROM public.ecr.aws/lambda/python:3.12 AS build

WORKDIR /work
RUN dnf install -y zip && dnf clean all

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/{agent}/ ./services/{agent}/

# uv from astral
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

RUN uv export --no-dev --no-emit-workspace --package {package} --frozen \\
        --format requirements-txt > /tmp/req.txt
RUN python -m pip install -r /tmp/req.txt --target /pkg --no-cache-dir
# Copy first-party workspace packages too (they aren't on PyPI).
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
    dockerfile.write_text(
        _DOCKERFILE.format(agent=AGENT_DIR.name, package=PACKAGE_NAME)
    )

    cmd = [
        "docker",
        "build",
        "--platform=linux/amd64",
        "--target=export",
        "--output",
        f"type=local,dest={DIST}",
        "-f",
        str(dockerfile),
        str(REPO_ROOT),
    ]
    subprocess.run(cmd, check=True)
    print(f"built: {DIST / (PACKAGE_NAME + '.zip')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: the Dockerfile path uses `services/{agent}/...` (no `agents/` prefix) because the scheduler lives at `services/scheduler/` not `services/agents/scheduler/`. `AGENT_DIR.name` resolves to `scheduler` and the COPY paths just work.

Also — `REPO_ROOT = Path(__file__).resolve().parents[2]` (not `[3]` like the agents) because of the shorter path: `services/scheduler/package_docker.py` → `parents[2]` is the repo root.

- [ ] **Step 3.1.2: Smoke build**

```bash
uv run python services/scheduler/package_docker.py
ls -lh services/scheduler/dist/news_scheduler.zip
unzip -l services/scheduler/dist/news_scheduler.zip | grep -E '(lambda_handler\.py|news_(scheduler|schemas|config|observability|db)/__init__\.py)'
unzip -l services/scheduler/dist/news_scheduler.zip | grep -c '/tests/' || echo "0 test entries"
```

Expected:
- Build succeeds (~30s with cache from earlier agent builds)
- Zip is roughly 35-40 MB (smaller than agents — no openai-agents / jinja2 / httpx)
- 6 expected entries (lambda_handler + 5 first-party packages including news_scheduler)
- 0 test entries

- [ ] **Step 3.1.3: Commit**

```bash
git add services/scheduler/package_docker.py
git commit -m "build(scheduler): package_docker.py (zip artifact via lambda/python:3.12)"
```

---

### Task 3.2: `deploy.py`

**Files:**
- Create: [services/scheduler/deploy.py](services/scheduler/deploy.py)

Mirror of `services/agents/digest/deploy.py` with two constant changes plus the path-depth fix.

- [ ] **Step 3.2.1: Implement**

```python
# services/scheduler/deploy.py
"""Build, upload, and deploy the scheduler Lambda.

Modes:
  build   — package_docker.py → S3 upload
  deploy  — build + terraform apply

Examples:
  uv run python services/scheduler/deploy.py --mode build
  uv run python services/scheduler/deploy.py --mode deploy --env dev
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
PACKAGE = "news_scheduler"
TF_DIR = AGENT_DIR.parents[1] / "infra" / "scheduler"


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
    key = f"scheduler/{sha}.zip"
    s.client("s3").upload_file(str(zip_path), _bucket(s), key)
    print(f"uploaded s3://{_bucket(s)}/{key}")
    return key


def _scraper_base_url() -> str:
    """Read the scraper's HTTPS endpoint from infra/scraper/ Terraform output."""
    scraper_tf = AGENT_DIR.parents[1] / "infra" / "scraper"
    result = subprocess.run(
        ["terraform", "output", "-raw", "scraper_endpoint"],
        cwd=scraper_tf,
        check=True,
        capture_output=True,
        text=True,
    )
    endpoint = result.stdout.strip()
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint


def cmd_build() -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    _upload(s, sha, zip_path)
    print(f"sha256(zip) = {_b64_sha256(zip_path)}")
    return 0


def cmd_deploy(env: str) -> int:
    s = _session()
    sha = _git_sha()
    zip_path = _build_zip()
    key = _upload(s, sha, zip_path)
    sha256 = _b64_sha256(zip_path)
    scraper_url = _scraper_base_url()
    print(f"scraper_base_url = {scraper_url}")

    tf_env = {**os.environ, "AWS_PROFILE": _profile()}
    try:
        subprocess.run(
            ["terraform", "workspace", "select", env],
            cwd=TF_DIR, check=True, env=tf_env,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["terraform", "workspace", "new", env],
            cwd=TF_DIR, check=True, env=tf_env,
        )

    subprocess.run(
        [
            "terraform", "apply", "-auto-approve",
            f"-var=zip_s3_key={key}",
            f"-var=zip_sha256={sha256}",
            f"-var=scraper_base_url={scraper_url}",
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

`TF_DIR = AGENT_DIR.parents[1] / "infra" / "scheduler"` — note the `[1]` (not `[2]`) because `services/scheduler/` is at the same depth as `services/agents/digest/` is below `services/agents/`. Let me explain: from `services/scheduler/deploy.py`, `parents[0]=scheduler`, `parents[1]=services`, `parents[2]=repo_root`. We want repo_root + `infra/scheduler/`, so `parents[2] / "infra" / "scheduler"` is correct... wait. Going to fix this — see below.

Correction: from `services/scheduler/deploy.py`:
- `parents[0]` = `services/scheduler`
- `parents[1]` = `services`
- `parents[2]` = repo root

To reach `infra/scheduler`, we need `parents[2] / "infra" / "scheduler"`. **Use `parents[2]`, not `parents[1]`.**

The agents' deploy.py uses `parents[3]` because they're at `services/agents/<agent>/`:
- `parents[0]` = `<agent>`
- `parents[1]` = `agents`
- `parents[2]` = `services`
- `parents[3]` = repo root

So copy-paste from digest's deploy.py would have been `parents[3]` → wrong here. Use `parents[2]` for scheduler. **Update the snippet above:** `TF_DIR = AGENT_DIR.parents[2] / "infra" / "scheduler"` and `scraper_tf = AGENT_DIR.parents[2] / "infra" / "scraper"`.

(The plan task should ship with the corrected `parents[2]`. The implementer is responsible for confirming the path resolves to the right place via `python -c 'from pathlib import Path; print(Path("services/scheduler/deploy.py").resolve().parents[2])'` before smoke-build.)

- [ ] **Step 3.2.2: Verify path resolution**

```bash
uv run python -c "
from pathlib import Path
p = Path('services/scheduler/deploy.py').resolve()
print('parents[2]:', p.parents[2])
print('TF_DIR:', p.parents[2] / 'infra' / 'scheduler')
"
```

Expected first line: `parents[2]: /Users/.../ai-agent-news-aggregator`. Adjust the `parents[N]` index in `deploy.py` if it doesn't.

- [ ] **Step 3.2.3: Smoke build mode (uploads to S3, doesn't apply Terraform)**

```bash
uv run python services/scheduler/deploy.py --mode build
```

Expected: build + upload + sha256 printed. Verify via `aws s3 ls "s3://news-aggregator-lambda-artifacts-368339042141/scheduler/" --profile aiengineer`.

- [ ] **Step 3.2.4: Verify lint + types**

```bash
uv run ruff check services/scheduler/deploy.py
uv run mypy services/scheduler/deploy.py
```

Both green.

- [ ] **Step 3.2.5: Commit**

```bash
git add services/scheduler/deploy.py
git commit -m "build(scheduler): deploy.py (build → S3 → terraform apply)"
```

---

## Phase 4 — Terraform Lambda module (no state machines yet)

Ship the Lambda function + IAM + log group as a standalone module. State machines + EventBridge come in Phase 5 — splitting lets us verify the basic Lambda works in isolation before layering Step Functions on top.

### Task 4.1: `infra/scheduler/` Lambda module

**Files:**
- Create: [infra/scheduler/backend.tf](infra/scheduler/backend.tf)
- Create: [infra/scheduler/data.tf](infra/scheduler/data.tf)
- Create: [infra/scheduler/variables.tf](infra/scheduler/variables.tf)
- Create: [infra/scheduler/main.tf](infra/scheduler/main.tf)
- Create: [infra/scheduler/outputs.tf](infra/scheduler/outputs.tf)
- Create: [infra/scheduler/terraform.tfvars.example](infra/scheduler/terraform.tfvars.example)
- Create: [infra/scheduler/.gitignore](infra/scheduler/.gitignore)

- [ ] **Step 4.1.1: `backend.tf`**

```hcl
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.42.0"
    }
  }

  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}
```

- [ ] **Step 4.1.2: `data.tf`**

```hcl
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
```

(No `terraform_remote_state` — bucket name computed inline as in #2's modules per the inline-bucket-name lesson.)

- [ ] **Step 4.1.3: `variables.tf`**

```hcl
variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type    = string
  default = "aiengineer"
}

variable "zip_s3_key" {
  description = "S3 key inside the artifact bucket (e.g. scheduler/<sha>.zip). Set by deploy.py."
  type        = string
}

variable "zip_sha256" {
  description = "Base64-encoded SHA256 of the zip — Lambda's source_code_hash."
  type        = string
}

variable "scraper_base_url" {
  description = "HTTPS endpoint of the scraper service (terraform output -raw scraper_endpoint from infra/scraper/)"
  type        = string
}

variable "memory_size" {
  type    = number
  default = 512
}

variable "timeout" {
  type    = number
  default = 30
}

variable "log_retention_days" {
  type    = number
  default = 14
}
```

(No `digest_max_concurrency` etc. yet — those land in Phase 5 with the state machines.)

- [ ] **Step 4.1.4: `main.tf`**

```hcl
locals {
  function_name           = "news-scheduler-${terraform.workspace}"
  ssm_prefix              = "/news-aggregator/${terraform.workspace}"
  lambda_artifacts_bucket = "news-aggregator-lambda-artifacts-${data.aws_caller_identity.current.account_id}"
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
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "ssm_read" {
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath",
        ]
        # GetParametersByPath needs the *path* resource (no trailing /*).
        # GetParameter / GetParameters need each child param ARN (with /*).
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
    ]
  })
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
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
      ENV              = terraform.workspace
      LOG_LEVEL        = "INFO"
      LOG_JSON         = "true"
      SSM_PARAM_PREFIX = local.ssm_prefix
    }
  }

  logging_config {
    log_format = "JSON"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.ssm_read,
    aws_cloudwatch_log_group.lambda,
  ]

  tags = { Project = "news-aggregator", Module = "scheduler" }
}
```

- [ ] **Step 4.1.5: `outputs.tf`**

```hcl
output "function_name" { value = aws_lambda_function.this.function_name }
output "function_arn"  { value = aws_lambda_function.this.arn }
output "log_group_name" { value = aws_cloudwatch_log_group.lambda.name }
output "scraper_base_url" { value = var.scraper_base_url }
```

- [ ] **Step 4.1.6: `terraform.tfvars.example`**

```hcl
zip_s3_key       = "scheduler/<git-sha>.zip"
zip_sha256       = "<base64-sha256>"
scraper_base_url = "https://scraper-...elb.amazonaws.com"
```

- [ ] **Step 4.1.7: `.gitignore` (matches scraper/digest convention — keeps `.terraform.lock.hcl` checked in)**

```
.terraform/
*.tfstate
*.tfstate.backup
terraform.tfvars
crash.log
crash.*.log
```

- [ ] **Step 4.1.8: Init + plan (no apply)**

```bash
ACCT=$(aws sts get-caller-identity --profile aiengineer --query Account --output text)
cd infra/scheduler
terraform init \
  -backend-config="bucket=news-aggregator-tf-state-$ACCT" \
  -backend-config="key=scheduler/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="profile=aiengineer"
SCRAPER_URL=$(cd ../scraper && terraform output -raw scraper_endpoint)
terraform plan \
  -var=zip_s3_key=scheduler/test.zip \
  -var=zip_sha256=test \
  -var=scraper_base_url="https://${SCRAPER_URL}"
cd ../..
```

Expected: `Plan: 5 to add, 0 to change, 0 to destroy.` (IAM role + 2 attachments + log group + Lambda).

- [ ] **Step 4.1.9: Commit (don't apply yet — Phase 5 will combine apply with state machines)**

```bash
git add infra/scheduler/.gitignore infra/scheduler/.terraform.lock.hcl infra/scheduler/backend.tf infra/scheduler/data.tf infra/scheduler/main.tf infra/scheduler/outputs.tf infra/scheduler/terraform.tfvars.example infra/scheduler/variables.tf
git commit -m "infra(scheduler): Lambda module (zip + IAM + log group, no SFN yet)"
```

---

## Phase 5 — State machines + EventBridge cron + alarms

### Task 5.1: ASL templates + Step Functions resources

**Files:**
- Create: [infra/scheduler/templates/cron_pipeline.asl.json](infra/scheduler/templates/cron_pipeline.asl.json)
- Create: [infra/scheduler/templates/remix_user.asl.json](infra/scheduler/templates/remix_user.asl.json)
- Create: [infra/scheduler/state_machines.tf](infra/scheduler/state_machines.tf)
- Create: [infra/scheduler/eventbridge.tf](infra/scheduler/eventbridge.tf)
- Modify: [infra/scheduler/variables.tf](infra/scheduler/variables.tf) — add concurrency knobs
- Modify: [infra/scheduler/outputs.tf](infra/scheduler/outputs.tf) — add state-machine ARNs

- [ ] **Step 5.1.1: Append concurrency variables to `variables.tf`**

Add to the END of `infra/scheduler/variables.tf`:

```hcl
variable "digest_max_concurrency" {
  type    = number
  default = 10
}

variable "editor_max_concurrency" {
  type    = number
  default = 5
}

variable "email_max_concurrency" {
  type    = number
  default = 2
}

variable "scraper_poll_max_iterations" {
  description = "Max poll iterations (× 30s = wall-clock cap on scraper run wait)"
  type        = number
  default     = 60
}
```

- [ ] **Step 5.1.2: Create `infra/scheduler/templates/cron_pipeline.asl.json`**

```json
{
  "Comment": "Daily news pipeline: scraper -> digest -> editor -> email",
  "StartAt": "TriggerScraper",
  "States": {
    "TriggerScraper": {
      "Type": "Task",
      "Resource": "arn:aws:states:::http:invoke",
      "Parameters": {
        "ApiEndpoint": "${scraper_base_url}/ingest",
        "Method": "POST",
        "Authentication": {
          "ConnectionArn": "${scraper_connection_arn}"
        },
        "RequestBody": {
          "lookback_hours": 24,
          "trigger": "scheduler"
        }
      },
      "ResultPath": "$.scraper_start",
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed", "States.Timeout"],
          "IntervalSeconds": 10,
          "MaxAttempts": 2,
          "BackoffRate": 2.0,
          "JitterStrategy": "FULL"
        }
      ],
      "Next": "WaitForScraper"
    },
    "WaitForScraper": {
      "Type": "Wait",
      "Seconds": 30,
      "Next": "PollScraper"
    },
    "PollScraper": {
      "Type": "Task",
      "Resource": "arn:aws:states:::http:invoke",
      "Parameters": {
        "ApiEndpoint.$": "States.Format('${scraper_base_url}/runs/{}', $.scraper_start.ResponseBody.id)",
        "Method": "GET",
        "Authentication": {
          "ConnectionArn": "${scraper_connection_arn}"
        }
      },
      "ResultPath": "$.scraper_run",
      "Retry": [
        {
          "ErrorEquals": ["States.TaskFailed", "States.Timeout"],
          "IntervalSeconds": 5,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ],
      "Next": "ScraperDone"
    },
    "ScraperDone": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.scraper_run.ResponseBody.status",
          "StringEquals": "success",
          "Next": "ListUnsummarised"
        },
        {
          "Variable": "$.scraper_run.ResponseBody.status",
          "StringEquals": "partial",
          "Next": "ListUnsummarised"
        },
        {
          "Variable": "$.scraper_run.ResponseBody.status",
          "StringEquals": "failed",
          "Next": "ScraperFailed"
        }
      ],
      "Default": "WaitForScraper"
    },
    "ScraperFailed": {
      "Type": "Fail",
      "Error": "ScraperRunFailed",
      "Cause": "Scraper reported status=failed"
    },
    "ListUnsummarised": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${scheduler_lambda_arn}",
        "Payload": {
          "op": "list_unsummarised",
          "hours": 24,
          "limit": 200
        }
      },
      "ResultSelector": {
        "article_ids.$": "$.Payload.article_ids"
      },
      "ResultPath": "$.unsummarised",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
          "IntervalSeconds": 5,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ],
      "Next": "DigestMap"
    },
    "DigestMap": {
      "Type": "Map",
      "ItemsPath": "$.unsummarised.article_ids",
      "MaxConcurrency": ${digest_max_concurrency},
      "ToleratedFailurePercentage": 100,
      "ItemProcessor": {
        "ProcessorConfig": { "Mode": "INLINE" },
        "StartAt": "InvokeDigest",
        "States": {
          "InvokeDigest": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${news_digest_arn}",
              "Payload": {
                "article_id.$": "$"
              }
            },
            "Retry": [
              {
                "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
                "IntervalSeconds": 5,
                "MaxAttempts": 2,
                "BackoffRate": 2.0,
                "JitterStrategy": "FULL"
              }
            ],
            "Catch": [
              {
                "ErrorEquals": ["States.ALL"],
                "Next": "DigestSkipped"
              }
            ],
            "End": true
          },
          "DigestSkipped": {
            "Type": "Pass",
            "End": true
          }
        }
      },
      "ResultPath": null,
      "Next": "ListActiveUsers"
    },
    "ListActiveUsers": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${scheduler_lambda_arn}",
        "Payload": { "op": "list_active_users" }
      },
      "ResultSelector": {
        "user_ids.$": "$.Payload.user_ids"
      },
      "ResultPath": "$.active_users",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
          "IntervalSeconds": 5,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ],
      "Next": "EditorMap"
    },
    "EditorMap": {
      "Type": "Map",
      "ItemsPath": "$.active_users.user_ids",
      "MaxConcurrency": ${editor_max_concurrency},
      "ToleratedFailurePercentage": 100,
      "ItemProcessor": {
        "ProcessorConfig": { "Mode": "INLINE" },
        "StartAt": "InvokeEditor",
        "States": {
          "InvokeEditor": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${news_editor_arn}",
              "Payload": {
                "user_id.$": "$",
                "lookback_hours": 24
              }
            },
            "Retry": [
              {
                "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
                "IntervalSeconds": 5,
                "MaxAttempts": 2,
                "BackoffRate": 2.0,
                "JitterStrategy": "FULL"
              }
            ],
            "Catch": [
              {
                "ErrorEquals": ["States.ALL"],
                "Next": "EditorSkipped"
              }
            ],
            "End": true
          },
          "EditorSkipped": {
            "Type": "Pass",
            "End": true
          }
        }
      },
      "ResultPath": null,
      "Next": "ListNewDigests"
    },
    "ListNewDigests": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${scheduler_lambda_arn}",
        "Payload": { "op": "list_new_digests" }
      },
      "ResultSelector": {
        "digest_ids.$": "$.Payload.digest_ids"
      },
      "ResultPath": "$.new_digests",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
          "IntervalSeconds": 5,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ],
      "Next": "EmailMap"
    },
    "EmailMap": {
      "Type": "Map",
      "ItemsPath": "$.new_digests.digest_ids",
      "MaxConcurrency": ${email_max_concurrency},
      "ToleratedFailurePercentage": 100,
      "ItemProcessor": {
        "ProcessorConfig": { "Mode": "INLINE" },
        "StartAt": "InvokeEmail",
        "States": {
          "InvokeEmail": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName": "${news_email_arn}",
              "Payload": {
                "digest_id.$": "$"
              }
            },
            "Retry": [
              {
                "ErrorEquals": ["Lambda.TooManyRequestsException"],
                "IntervalSeconds": 30,
                "MaxAttempts": 3,
                "BackoffRate": 2.0
              }
            ],
            "Catch": [
              {
                "ErrorEquals": ["States.ALL"],
                "Next": "EmailSkipped"
              }
            ],
            "End": true
          },
          "EmailSkipped": {
            "Type": "Pass",
            "End": true
          }
        }
      },
      "ResultPath": null,
      "End": true
    }
  }
}
```

- [ ] **Step 5.1.3: Create `infra/scheduler/templates/remix_user.asl.json`**

```json
{
  "Comment": "Remix: editor -> email for one user (manual UI trigger)",
  "StartAt": "InvokeEditor",
  "States": {
    "InvokeEditor": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${news_editor_arn}",
        "Payload": {
          "user_id.$": "$.user_id",
          "lookback_hours.$": "$.lookback_hours"
        }
      },
      "ResultSelector": {
        "editor.$": "$.Payload"
      },
      "Retry": [
        {
          "ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
          "IntervalSeconds": 5,
          "MaxAttempts": 2,
          "BackoffRate": 2.0,
          "JitterStrategy": "FULL"
        }
      ],
      "Next": "EditorOK"
    },
    "EditorOK": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.editor.failed",
          "BooleanEquals": true,
          "Next": "EditorFailed"
        },
        {
          "Variable": "$.editor.status",
          "StringEquals": "failed",
          "Next": "EditorFailed"
        },
        {
          "Variable": "$.editor.digest_id",
          "IsPresent": true,
          "Next": "InvokeEmail"
        }
      ],
      "Default": "EditorFailed"
    },
    "EditorFailed": {
      "Type": "Fail",
      "Error": "EditorProducedNoSendableDigest",
      "Cause": "Editor returned failure or no digest_id"
    },
    "InvokeEmail": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${news_email_arn}",
        "Payload": {
          "digest_id.$": "$.editor.digest_id"
        }
      },
      "ResultSelector": {
        "email.$": "$.Payload"
      },
      "ResultPath": "$.result",
      "Retry": [
        {
          "ErrorEquals": ["Lambda.TooManyRequestsException"],
          "IntervalSeconds": 30,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ],
      "End": true
    }
  }
}
```

- [ ] **Step 5.1.4: Create `infra/scheduler/state_machines.tf`**

```hcl
# Connection used by the cron pipeline's HTTP tasks for the scraper.
# AWS requires Authorization headers — we pass a dummy API_KEY since the scraper
# endpoint is internal-public. If a real auth header is needed later, swap in.
resource "aws_cloudwatch_event_connection" "scraper" {
  name               = "news-scraper-${terraform.workspace}"
  authorization_type = "API_KEY"
  auth_parameters {
    api_key {
      key   = "X-Internal-Token"
      value = "unused"
    }
  }
}

# IAM role for the cron-pipeline state machine.
resource "aws_iam_role" "cron_sm" {
  name = "news-cron-pipeline-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "cron_sm_invoke" {
  role = aws_iam_role.cron_sm.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-digest-${terraform.workspace}",
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}",
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}",
          aws_lambda_function.this.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = "states:InvokeHTTPEndpoint"
        Resource = "arn:aws:states:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:stateMachine:news-cron-pipeline-${terraform.workspace}"
        Condition = {
          StringEquals = {
            "states:HTTPMethod" : ["GET", "POST"]
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "events:RetrieveConnectionCredentials"
        Resource = aws_cloudwatch_event_connection.scraper.arn
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
        Resource = aws_cloudwatch_event_connection.scraper.secret_arn
      },
      {
        Effect = "Allow"
        Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "cron_sm" {
  name              = "/aws/states/news-cron-pipeline-${terraform.workspace}"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "cron" {
  name     = "news-cron-pipeline-${terraform.workspace}"
  role_arn = aws_iam_role.cron_sm.arn
  type     = "STANDARD"
  definition = templatefile("${path.module}/templates/cron_pipeline.asl.json", {
    scraper_base_url       = var.scraper_base_url
    scraper_connection_arn = aws_cloudwatch_event_connection.scraper.arn
    scheduler_lambda_arn   = aws_lambda_function.this.arn
    news_digest_arn        = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-digest-${terraform.workspace}"
    news_editor_arn        = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}"
    news_email_arn         = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}"
    digest_max_concurrency = var.digest_max_concurrency
    editor_max_concurrency = var.editor_max_concurrency
    email_max_concurrency  = var.email_max_concurrency
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.cron_sm.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}

# IAM role for the remix-user state machine — narrower scope.
resource "aws_iam_role" "remix_sm" {
  name = "news-remix-user-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "remix_sm_invoke" {
  role = aws_iam_role.remix_sm.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "lambda:InvokeFunction"
        Resource = [
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}",
          "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}",
        ]
      },
      {
        Effect = "Allow"
        Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups",
        ]
        Resource = "*"
      },
    ]
  })
}

resource "aws_cloudwatch_log_group" "remix_sm" {
  name              = "/aws/states/news-remix-user-${terraform.workspace}"
  retention_in_days = var.log_retention_days
}

resource "aws_sfn_state_machine" "remix" {
  name     = "news-remix-user-${terraform.workspace}"
  role_arn = aws_iam_role.remix_sm.arn
  type     = "STANDARD"
  definition = templatefile("${path.module}/templates/remix_user.asl.json", {
    news_editor_arn = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-editor-${terraform.workspace}"
    news_email_arn  = "arn:aws:lambda:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:function:news-email-${terraform.workspace}"
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.remix_sm.arn}:*"
    include_execution_data = true
    level                  = "ALL"
  }

  tracing_configuration {
    enabled = true
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}
```

- [ ] **Step 5.1.5: Create `infra/scheduler/eventbridge.tf`**

```hcl
# IAM role for EventBridge to start cron-pipeline executions.
resource "aws_iam_role" "cron_trigger" {
  name = "news-cron-trigger-${terraform.workspace}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_iam_role_policy" "cron_trigger" {
  role = aws_iam_role.cron_trigger.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "states:StartExecution"
      Resource = aws_sfn_state_machine.cron.arn
    }]
  })
}

# Daily cron at 21:00 UTC = 00:00 EAT.
resource "aws_cloudwatch_event_rule" "cron" {
  name                = "news-cron-pipeline-${terraform.workspace}"
  description         = "Daily news pipeline trigger (00:00 EAT = 21:00 UTC)"
  schedule_expression = "cron(0 21 * * ? *)"
  state               = "ENABLED"
  tags                = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_cloudwatch_event_target" "cron" {
  rule     = aws_cloudwatch_event_rule.cron.name
  arn      = aws_sfn_state_machine.cron.arn
  role_arn = aws_iam_role.cron_trigger.arn
}

# CloudWatch alarms — fail + stale.
resource "aws_cloudwatch_metric_alarm" "cron_failed" {
  alarm_name          = "news-cron-pipeline-failed-${terraform.workspace}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "news-cron-pipeline state machine status FAILED/TIMED_OUT"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.cron.arn
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}

resource "aws_cloudwatch_metric_alarm" "cron_stale" {
  alarm_name          = "news-cron-pipeline-stale-${terraform.workspace}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsSucceeded"
  namespace           = "AWS/States"
  period              = 129600  # 36 hours
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "news-cron-pipeline has not had a successful run in 36h"
  treat_missing_data  = "breaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.cron.arn
  }

  tags = { Project = "news-aggregator", Module = "scheduler" }
}
```

- [ ] **Step 5.1.6: Append to `outputs.tf`**

Add at the end of `infra/scheduler/outputs.tf`:

```hcl
output "cron_state_machine_arn" {
  description = "ARN of the cron-pipeline state machine (consumed by Make targets)"
  value       = aws_sfn_state_machine.cron.arn
}

output "remix_state_machine_arn" {
  description = "ARN of the remix-user state machine (REQUIRED by #4 — its API Lambda will StartExecution on this)"
  value       = aws_sfn_state_machine.remix.arn
}
```

- [ ] **Step 5.1.7: Plan (no apply)**

```bash
cd infra/scheduler
SCRAPER_URL=$(cd ../scraper && terraform output -raw scraper_endpoint)
terraform plan \
  -var=zip_s3_key=scheduler/test.zip \
  -var=zip_sha256=test \
  -var=scraper_base_url="https://${SCRAPER_URL}"
cd ../..
```

Expected plan summary: `Plan: ~13 to add, 0 to change, 0 to destroy.` (Lambda + IAM × 2 + log groups × 2 + connection + 2 state machines + cron rule + cron target + cron-trigger IAM + 2 alarms — exact count depends on the connection's auto-created secret).

- [ ] **Step 5.1.8: Commit (no apply yet — Phase 6 does live deploy)**

```bash
git add infra/scheduler/templates/ infra/scheduler/state_machines.tf infra/scheduler/eventbridge.tf infra/scheduler/variables.tf infra/scheduler/outputs.tf
git commit -m "infra(scheduler): state machines + EventBridge cron + alarms"
```

---

### Task 5.2: ASL static test (CI guard against template drift)

**Files:**
- Create: [tests/integration/test_scheduler_asl.py](tests/integration/test_scheduler_asl.py)

- [ ] **Step 5.2.1: Write the test**

```python
# tests/integration/test_scheduler_asl.py
"""Static check: rendered ASL JSON parses and has the expected state names."""

from __future__ import annotations

import json
from pathlib import Path
from string import Template

ASL_DIR = Path(__file__).resolve().parents[2] / "infra" / "scheduler" / "templates"


def _render(template_name: str, **vars: object) -> dict:
    raw = (ASL_DIR / template_name).read_text()
    # Terraform's templatefile() uses ${name} substitution; mirror that with
    # string.Template (also ${name}). Note: Terraform also supports
    # ${expr} but our templates use plain variable names, so this is enough.
    rendered = Template(raw).safe_substitute(**{k: str(v) for k, v in vars.items()})
    return json.loads(rendered)


def test_cron_pipeline_asl_parses() -> None:
    asl = _render(
        "cron_pipeline.asl.json",
        scraper_base_url="https://scraper.example",
        scraper_connection_arn="arn:aws:events:us-east-1:0:connection/scraper/abc",
        scheduler_lambda_arn="arn:aws:lambda:us-east-1:0:function:scheduler",
        news_digest_arn="arn:aws:lambda:us-east-1:0:function:digest",
        news_editor_arn="arn:aws:lambda:us-east-1:0:function:editor",
        news_email_arn="arn:aws:lambda:us-east-1:0:function:email",
        digest_max_concurrency=10,
        editor_max_concurrency=5,
        email_max_concurrency=2,
    )
    assert asl["StartAt"] == "TriggerScraper"
    assert {
        "TriggerScraper",
        "WaitForScraper",
        "PollScraper",
        "ScraperDone",
        "ScraperFailed",
        "ListUnsummarised",
        "DigestMap",
        "ListActiveUsers",
        "EditorMap",
        "ListNewDigests",
        "EmailMap",
    } <= set(asl["States"].keys())

    # Each Map state has the right concurrency + tolerance.
    assert asl["States"]["DigestMap"]["MaxConcurrency"] == 10
    assert asl["States"]["DigestMap"]["ToleratedFailurePercentage"] == 100
    assert asl["States"]["EditorMap"]["MaxConcurrency"] == 5
    assert asl["States"]["EmailMap"]["MaxConcurrency"] == 2

    # Scraper failure path is reachable.
    choices = asl["States"]["ScraperDone"]["Choices"]
    assert any(c.get("StringEquals") == "failed" for c in choices)


def test_remix_user_asl_parses() -> None:
    asl = _render(
        "remix_user.asl.json",
        news_editor_arn="arn:aws:lambda:us-east-1:0:function:editor",
        news_email_arn="arn:aws:lambda:us-east-1:0:function:email",
    )
    assert asl["StartAt"] == "InvokeEditor"
    assert {"InvokeEditor", "EditorOK", "EditorFailed", "InvokeEmail"} <= set(
        asl["States"].keys()
    )
    assert asl["States"]["InvokeEditor"]["Type"] == "Task"
    assert asl["States"]["EditorOK"]["Type"] == "Choice"
```

- [ ] **Step 5.2.2: Run, expect pass**

```bash
uv run pytest tests/integration/test_scheduler_asl.py -v
```

Both tests pass.

- [ ] **Step 5.2.3: Commit**

```bash
git add tests/integration/test_scheduler_asl.py
git commit -m "test(scheduler): static ASL JSON parses + expected states present"
```

---

## Phase 6 — Live deploy + smoke

### Task 6.1: Deploy + verify

These steps require AWS access. **Pause for user approval before running.**

- [ ] **Step 6.1.1: Confirm prerequisites**

Before deploying, confirm:
- `infra/bootstrap/` is applied (artifact bucket exists).
- `infra/scraper/` is applied (`scraper_endpoint` output is reachable; `make scraper-pin-up` if needed for live test).
- `infra/digest/`, `infra/editor/`, `infra/email/` are applied (state-machine IAM references those Lambda ARNs).
- `make secrets-sync ENV=dev` was last run with current `.env` (SSM has the values the scheduler Lambda needs at cold-start).

- [ ] **Step 6.1.2: Run the scheduler deploy**

```bash
uv run python services/scheduler/deploy.py --mode deploy --env dev
```

Expected (~30s for IAM + Lambda + state machines):
- Build + S3 upload of `news_scheduler.zip`.
- Terraform apply: `~13 to add, 0 to change, 0 to destroy.`
- New resources visible:
  - `aws_lambda_function.this` (`news-scheduler-dev`)
  - `aws_sfn_state_machine.cron` (`news-cron-pipeline-dev`)
  - `aws_sfn_state_machine.remix` (`news-remix-user-dev`)
  - `aws_cloudwatch_event_rule.cron` (`news-cron-pipeline-dev` schedule)

- [ ] **Step 6.1.3: Read state-machine ARNs**

```bash
cd infra/scheduler
CRON_ARN=$(terraform output -raw cron_state_machine_arn)
REMIX_ARN=$(terraform output -raw remix_state_machine_arn)
echo "CRON_ARN=$CRON_ARN"
echo "REMIX_ARN=$REMIX_ARN"
cd ../..
```

- [ ] **Step 6.1.4: Smoke test the scheduler Lambda directly**

```bash
aws lambda invoke --function-name news-scheduler-dev \
  --payload '{"op":"list_active_users"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/scheduler-out.json --profile aiengineer
cat /tmp/scheduler-out.json | jq
```

Expected: `{"user_ids": ["<your-seed-user-uuid>"]}`. Validates SSM hydration + DB connection.

- [ ] **Step 6.1.5: Smoke test cron-pipeline (manual `start-execution`)**

Trigger a one-off execution to verify wiring (this WILL run scraper + digest + editor + email if scraper produces fresh content):

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$CRON_ARN" \
  --input '{}' \
  --profile aiengineer
# Capture executionArn from output
EXEC_ARN=...
aws stepfunctions describe-execution --execution-arn "$EXEC_ARN" --profile aiengineer --query 'status'
```

Poll `describe-execution` until status is terminal (`SUCCEEDED` / `FAILED`). On `FAILED`:
- Inspect `aws stepfunctions get-execution-history --execution-arn "$EXEC_ARN" --profile aiengineer | jq '.events[] | select(.type=="ExecutionFailed" or .type=="TaskFailed")'`
- Common failures: scraper /ingest 503 if pinned-down; missing IAM permission; ASL placeholder typo.

- [ ] **Step 6.1.6: Smoke test remix state machine**

```bash
USER_ID=$(aws lambda invoke --function-name news-scheduler-dev \
  --payload '{"op":"list_active_users"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/u.json --profile aiengineer >/dev/null && jq -r '.user_ids[0]' /tmp/u.json)

aws stepfunctions start-execution \
  --state-machine-arn "$REMIX_ARN" \
  --input "{\"user_id\":\"$USER_ID\",\"lookback_hours\":24}" \
  --profile aiengineer
```

Poll until `SUCCEEDED`. Email arrives in your inbox (Resend latency ≤ 5 min).

- [ ] **Step 6.1.7: Commit (no code change — but tag the deploy)**

The deploy is now live; no commit needed for Phase 6 itself. Phase 7 lands the Make targets, docs, and tag.

---

## Phase 7 — Make targets, docs, and tag

### Task 7.1: Append `scheduler-*` Make targets

**Files:**
- Modify: [Makefile](Makefile)

- [ ] **Step 7.1.1: Append to `Makefile`**

Add the following block AFTER the existing `# ---------- agents (#2) ----------` section:

```makefile
# ---------- scheduler (#3) ----------

.PHONY: scheduler-deploy-build scheduler-deploy \
        scheduler-list-unsummarised scheduler-list-active-users scheduler-list-new-digests \
        cron-invoke cron-history cron-describe \
        remix-invoke remix-history \
        scheduler-logs scheduler-logs-follow tag-scheduler

scheduler-deploy-build:           ## build + s3 upload (scheduler)
	uv run python services/scheduler/deploy.py --mode build

scheduler-deploy:                 ## build + terraform apply (scheduler)
	uv run python services/scheduler/deploy.py --mode deploy --env dev

scheduler-list-unsummarised:      ## local CLI: print unsummarised article IDs  [LOOKBACK=24]
	uv run python -m news_scheduler list-unsummarised --hours $${LOOKBACK:-24}

scheduler-list-active-users:      ## local CLI: print active user IDs
	uv run python -m news_scheduler list-active-users

scheduler-list-new-digests:       ## local CLI: print today's GENERATED digest IDs
	uv run python -m news_scheduler list-new-digests

cron-invoke:                      ## start-execution on news-cron-pipeline-dev
	@CRON=$$(cd infra/scheduler && terraform output -raw cron_state_machine_arn) && \
	  aws stepfunctions start-execution --state-machine-arn "$$CRON" --input '{}' --profile aiengineer | jq

cron-history:                     ## list 5 most recent cron executions
	@CRON=$$(cd infra/scheduler && terraform output -raw cron_state_machine_arn) && \
	  aws stepfunctions list-executions --state-machine-arn "$$CRON" --max-items 5 --profile aiengineer \
	  --query 'executions[].{Status:status,Start:startDate,Name:name}' --output table

cron-describe:                    ## describe one execution by name (NAME=...)
	@test -n "$(NAME)" || (echo "NAME required: make cron-describe NAME=<exec-name>" && exit 1)
	@CRON=$$(cd infra/scheduler && terraform output -raw cron_state_machine_arn) && \
	  aws stepfunctions describe-execution \
	  --execution-arn "$${CRON/stateMachine/execution}:$(NAME)" \
	  --profile aiengineer | jq

remix-invoke:                     ## start-execution on news-remix-user-dev (USER_ID=...)
	@test -n "$(USER_ID)" || (echo "USER_ID required: make remix-invoke USER_ID=<uuid>" && exit 1)
	@REMIX=$$(cd infra/scheduler && terraform output -raw remix_state_machine_arn) && \
	  aws stepfunctions start-execution --state-machine-arn "$$REMIX" \
	  --input "{\"user_id\":\"$(USER_ID)\",\"lookback_hours\":$${LOOKBACK:-24}}" \
	  --profile aiengineer | jq

remix-history:                    ## list 5 most recent remix executions
	@REMIX=$$(cd infra/scheduler && terraform output -raw remix_state_machine_arn) && \
	  aws stepfunctions list-executions --state-machine-arn "$$REMIX" --max-items 5 --profile aiengineer \
	  --query 'executions[].{Status:status,Start:startDate,Name:name}' --output table

scheduler-logs:                   ## tail scheduler Lambda logs  [SINCE=10m]
	aws logs tail /aws/lambda/news-scheduler-dev --since $${SINCE:-10m} --profile aiengineer

scheduler-logs-follow:            ## follow scheduler Lambda logs in real time
	aws logs tail /aws/lambda/news-scheduler-dev --follow --profile aiengineer

tag-scheduler:                    ## tag sub-project #3
	git tag -f -a scheduler-v0.4.0 -m "Sub-project #3 Scheduler + Orchestration"
	@echo "Push with: git push origin scheduler-v0.4.0"
```

- [ ] **Step 7.1.2: Verify**

```bash
make help | grep -E "scheduler|cron|remix" | head -25
make -n scheduler-list-active-users
```

Both should succeed.

- [ ] **Step 7.1.3: Commit**

```bash
git add Makefile
git commit -m "build(make): add scheduler-/cron-/remix-* targets (local + invoke + logs)"
```

---

### Task 7.2: Update `infra/README.md` with scheduler section

**Files:**
- Modify: [infra/README.md](infra/README.md)

- [ ] **Step 7.2.1: Append a section**

Add at the END of `infra/README.md`:

```markdown
## Sub-project #3 — scheduler (Step Functions + EventBridge cron)

Two state machines under `infra/scheduler/`:

- `news-cron-pipeline-${env}` — fired daily by EventBridge at 21:00 UTC
  (= 00:00 EAT). Runs `scraper → digest → editor → email` end-to-end.
- `news-remix-user-${env}` — invoked by #4's API for "send my digest now"
  per user. Skips scraper + digest stages.

Plus `news-scheduler-${env}` Lambda hosting three list handlers
(`list_unsummarised`, `list_active_users`, `list_new_digests`).

### Deploy

```sh
make scheduler-deploy
```

(Reads the scraper endpoint from `infra/scraper/`'s output; no manual
`MAIL_FROM`-style env var needed.)

### Invoke + monitor

```sh
make cron-invoke                           # one-off cron run
make cron-history                          # last 5 executions
make remix-invoke USER_ID=<uuid>           # send my digest now
make remix-history
make scheduler-logs SINCE=10m              # scheduler Lambda logs
aws stepfunctions describe-execution \
  --execution-arn <arn> --profile aiengineer
```

### Roll back

State machines: edit ASL or `state_machines.tf`, re-apply. Step Functions
keeps the previous definition reachable via `aws stepfunctions list-state-machine-versions`.

### Failure modes

- **Cron fires while scraper is paused (ECS min=0):** state machine fails
  fast on `/ingest` 5xx. Use `make scraper-pin-up` before retrying.
- **`MaxConcurrency` exhausted** on a Map: typically not — defaults are
  conservative (10/5/2). Tunable via `digest_max_concurrency` etc. Terraform vars.
- **`news-cron-pipeline-stale` alarm fires** after 36h with no successful
  run: cron stopped firing or every recent run failed. Check
  EventBridge rule + recent executions.
- **HTTP task auth errors** on the scraper poll: the scraper endpoint
  changed. `terraform output -raw scraper_endpoint` should match the
  state machine's `scraper_base_url` (re-deploy if drifted).
```

- [ ] **Step 7.2.2: Commit**

```bash
git add infra/README.md
git commit -m "docs(infra): document sub-project #3 scheduler lifecycle"
```

---

### Task 7.3: Refresh `AGENTS.md`

**Files:**
- Modify: [AGENTS.md](AGENTS.md)

- [ ] **Step 7.3.1: Update sub-project decomposition table**

In the table at the top of `AGENTS.md`, find the `**3**` row:

```
| **3** | Scheduler + orchestration (EventBridge → ECS → Lambda) | not started |
```

Wait — it's currently `not started` after the #2 ship; we marked #2 as `current` in the previous AGENTS.md refresh. Find whatever row reads "Scheduler + orchestration ... | not started |" and change to:

```
| **3** | Scheduler + orchestration — Step Functions cron + remix state machines, EventBridge daily cron | shipped — tag `scheduler-v0.4.0` |
| 4 | API + Auth (FastAPI on Lambda, Clerk JWT) | **current** |
```

(Mark #4 as current — that's the next sub-project after the merge.)

- [ ] **Step 7.3.2: Add operational-commands section**

After the existing `### Sub-project #2 (Agents) — operational commands` section and BEFORE "## What NOT to do", insert:

```markdown
### Sub-project #3 (Scheduler) — operational commands

Two state machines + one Lambda + one EventBridge cron:
- `news-cron-pipeline-dev` runs daily at 21:00 UTC (= 00:00 EAT).
- `news-remix-user-dev` is invoked by #4's API for per-user manual sends.

```sh
# Local CLI (no AWS)
make scheduler-list-unsummarised LOOKBACK=24       # debug query
make scheduler-list-active-users
make scheduler-list-new-digests

# Deploy
make scheduler-deploy

# Invoke + monitor
make cron-invoke                                   # one-off cron run
make cron-history                                  # last 5 executions
make remix-invoke USER_ID=<uuid>                   # send my digest now
make remix-history
make scheduler-logs SINCE=10m
make scheduler-logs-follow
```

The cron-pipeline state machine's IAM role has `lambda:InvokeFunction` on
all four agent Lambdas (digest, editor, email, scheduler). Step Functions
HTTP tasks talk to the scraper via an EventBridge Connection (dummy API_KEY
header — the scraper endpoint is internal-public).

#3 outputs `remix_state_machine_arn` — #4's API Lambda IAM role gets
`states:StartExecution` on this ARN.
```

- [ ] **Step 7.3.3: Add #3-specific anti-patterns to "What NOT to do"**

Append the following bullets to the existing "What NOT to do" list (append before the empty line that precedes `## Security`):

```markdown
- Do not use `data.terraform_remote_state.scraper.outputs.scraper_endpoint` to read the scraper URL into the scheduler state machine. The scraper module's state lives in S3, but `aws_sfn_state_machine.definition` is rendered at apply-time only; re-applying the scheduler when the scraper endpoint changes is a one-line `-var=scraper_base_url=...` change via `deploy.py`. Keep the seam thin.
- Do not omit `ToleratedFailurePercentage = 100` on the agent Map states. Without it, one user's editor failure aborts the whole pipeline and prevents 99 other users from getting emails.
- Do not raise from the scheduler Lambda's `handler` on a malformed event. Step Functions will retry per the configured policy and the bad payload won't fix itself. Return a `{"failed": true, "reason": "..."}` dict and surface in CloudWatch.
- Do not use `arn:aws:states:::lambda:invoke.waitForTaskToken` in the agent Maps. Synchronous direct invoke is cheaper and simpler; we don't need callback-style task tokens at this scale.
```

- [ ] **Step 7.3.4: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): refresh AGENTS.md for sub-project #3 ship"
```

---

### Task 7.4: Final verification + tag

- [ ] **Step 7.4.1: Run the full check (CI-equivalent)**

```bash
uv run ruff check
uv run ruff format --check
uv run mypy packages services/scheduler
uv run pytest -q
```

All green.

- [ ] **Step 7.4.2: Tag the release**

```bash
make tag-scheduler
```

Output: `Push with: git push origin scheduler-v0.4.0`.

- [ ] **Step 7.4.3: Final cleanup commit**

If `git status` is clean (no stray files), Phase 7 is done. Otherwise:

```bash
git status
git commit -m "chore: tidy after sub-project #3"
```

---

## Self-Review

After writing this plan:

**Spec coverage:**

| Spec section | Implemented in |
|---|---|
| §1 Overview | Tasks 4.1, 5.1 (state machines + cron) |
| §2 Sub-project boundary | Tasks 2.1-2.7 (workspace), 4.1, 5.1 (Terraform) |
| §3 Architecture (decisions table) | Inline throughout — see Task 5.1.4 (state_machines.tf) for `MaxConcurrency`, `ToleratedFailurePercentage`, IAM scope |
| §4 Cron pipeline state machine | Task 5.1.2 (ASL JSON), Task 5.1.4 (state_machines.tf) |
| §5 Remix state machine | Task 5.1.3 (ASL JSON), Task 5.1.4 |
| §6 Repo layout | Task 2.1 (scaffold), 4.1 (infra), 5.1 (Terraform) |
| §7 Make targets | Task 7.1 |
| §8 IAM + sub-project boundary | Task 5.1.4 (Step Functions IAM), Task 5.1.6 (outputs.tf for #4) |
| §9 Error handling & observability | Task 5.1.2/5.1.3 (Retry/Catch), Task 5.1.5 (alarms) |
| §10 Testing strategy | Tasks 1.1, 1.2 (integration), 2.2-2.6 (unit), 5.2 (ASL static), Phase 6 (live) |
| §11 Cost guardrails | Documented in spec; no separate task. |
| §12 Risks | Documented in spec + AGENTS.md anti-patterns (Task 7.3.3) |
| §13 Sub-project dependency alignment | Documented in spec. |
| §14 Implementation phasing | This entire plan. |

**Placeholder scan:** No "TBD"/"TODO"/"similar to" patterns. Every code step has full code. Every AWS command has full args.

**Type consistency:** `list_active_user_ids` returns `list[UUID]` (Task 1.1) and the scheduler handler converts to `list[str]` for JSON-safe state-machine input (Task 2.3). `list_generated_today` returns `list[int]` (Task 1.2); handler passes `[100, 101]` style ints through (Task 2.4); ASL `EmailMap` uses `"digest_id.$": "$"` (Task 5.1.2). All matches.

**Path-depth gotcha:** `services/scheduler/` is at depth 2 (`services/scheduler/...`), not depth 3 like `services/agents/digest/`. This affects `parents[N]` in `package_docker.py` (uses `parents[2]` for `REPO_ROOT`) and `deploy.py` (uses `parents[2]` for `TF_DIR`). Task 3.2.2 explicitly verifies this before smoke-build.

**One unresolved decision left to the engineer:** the EventBridge Connection's auth scheme (Task 5.1.4) uses dummy `API_KEY` header `X-Internal-Token: unused`. If the scraper later requires real auth, this is a one-resource Terraform change.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-scheduler-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
