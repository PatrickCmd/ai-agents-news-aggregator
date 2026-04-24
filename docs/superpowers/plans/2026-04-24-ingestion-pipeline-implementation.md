# Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `services/scraper/` — a single ECS Express-mode service (FastAPI + CLI + three pipelines) that populates the `articles` table from YouTube RSS, blog RSS (via rss-mcp), and a curated list of websites (via Playwright MCP + OpenAI Agents SDK).

**Architecture:** Thin FastAPI/CLI adapters delegate to pure pipeline objects that take I/O adapters via constructor injection. Pipelines normalize to `ArticleIn` and call `ArticleRepository.upsert_many`. Run bookkeeping lives in a new `scraper_runs` table. LLM usage and cost tracking for the web-search agent route through a new `news_observability.costs` module. Adapter-seam pattern keeps CI fast (no MCP subprocesses in default test runs).

**Tech Stack:** Python 3.12 / uv workspace / SQLAlchemy 2.x async / Alembic / Pydantic v2 / FastAPI / Typer / OpenAI Agents SDK / Playwright MCP / rss-mcp / pytest + testcontainers-postgres

**Design spec:** [docs/superpowers/specs/2026-04-24-ingestion-pipeline-design.md](../specs/2026-04-24-ingestion-pipeline-design.md)

---

## Working conventions

- Branch: `sub-project#1` (already created by the user).
- After every task with a green test, commit. Conventional Commits (`feat(scraper): ...`, `test(scraper): ...`, etc.).
- **Definition of done for a task:** all its listed tests pass locally AND `uv run ruff check`, `uv run ruff format --check`, `uv run mypy packages services/scraper/src` all pass.
- Before each task, run `make check` briefly to confirm baseline is green.
- Every test uses `pytest.mark.asyncio` when async (asyncio_mode is `auto`, but mark is still required for mypy sanity).

---

## Phase 1 — `scraper_runs` schema, model, migration, repository

### Task 1.1: Add Pydantic schemas for scraper_run

**Files:**
- Create: `packages/schemas/src/news_schemas/scraper_run.py`
- Create: `packages/schemas/src/news_schemas/tests/test_scraper_run.py`

- [ ] **Step 1: Write failing tests**

Create `packages/schemas/src/news_schemas/tests/test_scraper_run.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    RunStats,
    ScraperRunIn,
    ScraperRunOut,
    ScraperRunStatus,
    WebSearchStats,
    YouTubeStats,
)


def test_pipeline_stats_defaults() -> None:
    s = PipelineStats(status=ScraperRunStatus.SUCCESS)
    assert s.fetched == 0
    assert s.errors == []
    assert s.status is ScraperRunStatus.SUCCESS


def test_youtube_stats_extends_pipeline_stats() -> None:
    s = YouTubeStats(status=ScraperRunStatus.SUCCESS, transcripts_fetched=3)
    assert s.transcripts_fetched == 3
    assert s.transcripts_failed == 0


def test_web_search_stats_has_cost_fields() -> None:
    s = WebSearchStats(
        status=ScraperRunStatus.PARTIAL,
        sites_attempted=2,
        sites_succeeded=1,
        items_extracted=5,
        total_input_tokens=100,
        total_output_tokens=50,
        total_cost_usd=0.001,
    )
    assert s.total_cost_usd == pytest.approx(0.001)


def test_run_stats_all_optional() -> None:
    rs = RunStats()
    assert rs.youtube is None
    assert rs.rss is None
    assert rs.web_search is None


def test_scraper_run_in_valid() -> None:
    ri = ScraperRunIn(
        trigger="api",
        lookback_hours=24,
        pipelines_requested=[PipelineName.YOUTUBE, PipelineName.RSS],
    )
    assert ri.pipelines_requested == [PipelineName.YOUTUBE, PipelineName.RSS]


def test_scraper_run_out_round_trips() -> None:
    rid = uuid4()
    started = datetime.now(UTC)
    ro = ScraperRunOut(
        id=rid,
        trigger="cli",
        status=ScraperRunStatus.RUNNING,
        started_at=started,
        completed_at=None,
        lookback_hours=12,
        pipelines_requested=[PipelineName.WEB_SEARCH],
        stats=RunStats(),
        error_message=None,
    )
    assert ro.id == rid
    assert ro.status is ScraperRunStatus.RUNNING
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest packages/schemas/src/news_schemas/tests/test_scraper_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_schemas.scraper_run'`

- [ ] **Step 3: Implement schemas**

Create `packages/schemas/src/news_schemas/scraper_run.py`:

```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScraperRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class PipelineName(StrEnum):
    YOUTUBE = "youtube"
    RSS = "rss"
    WEB_SEARCH = "web_search"


class PipelineStats(BaseModel):
    status: ScraperRunStatus
    fetched: int = 0
    kept: int = 0
    inserted: int = 0
    skipped_old: int = 0
    duration_seconds: float = 0.0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class YouTubeStats(PipelineStats):
    transcripts_fetched: int = 0
    transcripts_failed: int = 0


class WebSearchStats(PipelineStats):
    sites_attempted: int = 0
    sites_succeeded: int = 0
    items_extracted: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


class RunStats(BaseModel):
    youtube: YouTubeStats | None = None
    rss: PipelineStats | None = None
    web_search: WebSearchStats | None = None


class ScraperRunIn(BaseModel):
    trigger: str
    lookback_hours: int = 24
    pipelines_requested: list[PipelineName]


class ScraperRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trigger: str
    status: ScraperRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    lookback_hours: int
    pipelines_requested: list[PipelineName]
    stats: RunStats
    error_message: str | None = None
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest packages/schemas/src/news_schemas/tests/test_scraper_run.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/schemas/src/news_schemas/scraper_run.py \
        packages/schemas/src/news_schemas/tests/test_scraper_run.py
git commit -m "feat(schemas): add scraper_run contracts for sub-project #1"
```

---

### Task 1.2: Add ScraperRun SQLAlchemy model

**Files:**
- Create: `packages/db/src/news_db/models/scraper_run.py`
- Modify: `packages/db/src/news_db/models/__init__.py`

- [ ] **Step 1: Write the model**

Create `packages/db/src/news_db/models/scraper_run.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, CheckConstraint, DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from news_db.models.base import Base


class ScraperRun(Base):
    __tablename__ = "scraper_runs"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lookback_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    pipelines_requested: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False
    )
    stats: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status in ('running','success','partial','failed')",
            name="scraper_runs_status_check",
        ),
        Index("ix_scraper_runs_started", "started_at"),
    )
```

- [ ] **Step 2: Register in models/__init__.py**

Replace the contents of `packages/db/src/news_db/models/__init__.py` with:

```python
"""Re-export all ORM models so Alembic autogenerate can see them."""

from news_db.models.article import Article
from news_db.models.audit_log import AuditLog
from news_db.models.base import Base
from news_db.models.digest import Digest
from news_db.models.email_send import EmailSend
from news_db.models.scraper_run import ScraperRun
from news_db.models.user import User

__all__ = ["Article", "AuditLog", "Base", "Digest", "EmailSend", "ScraperRun", "User"]
```

- [ ] **Step 3: Smoke-import — verify it loads**

Run: `uv run python -c "from news_db.models import ScraperRun; print(ScraperRun.__tablename__)"`
Expected: `scraper_runs`

- [ ] **Step 4: Commit**

```bash
git add packages/db/src/news_db/models/scraper_run.py \
        packages/db/src/news_db/models/__init__.py
git commit -m "feat(db): add ScraperRun SQLAlchemy model"
```

---

### Task 1.3: Add Alembic migration 0002 for scraper_runs

**Files:**
- Create: `packages/db/src/news_db/alembic/versions/0002_scraper_runs.py`
- Modify: `tests/integration/conftest.py` (extend TRUNCATE list)
- Create: `tests/integration/test_scraper_runs_migration.py`

- [ ] **Step 1: Write the migration**

Create `packages/db/src/news_db/alembic/versions/0002_scraper_runs.py`:

```python
"""scraper_runs — ingestion run bookkeeping

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scraper_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="running"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lookback_hours", sa.Integer, nullable=False),
        sa.Column(
            "pipelines_requested",
            postgresql.ARRAY(sa.Text),
            nullable=False,
        ),
        sa.Column(
            "stats",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status in ('running','success','partial','failed')",
            name="scraper_runs_status_check",
        ),
    )
    op.create_index("ix_scraper_runs_started", "scraper_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_scraper_runs_started", table_name="scraper_runs")
    op.drop_table("scraper_runs")
```

- [ ] **Step 2: Extend conftest TRUNCATE**

Edit `tests/integration/conftest.py` and change the TRUNCATE string (line ~62) from:

```python
"truncate table audit_logs, email_sends, digests, articles, users "
"restart identity cascade"
```

to:

```python
"truncate table audit_logs, email_sends, digests, articles, scraper_runs, users "
"restart identity cascade"
```

- [ ] **Step 3: Write migration up/down test**

Create `tests/integration/test_scraper_runs_migration.py`:

```python
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_scraper_runs_table_exists(session: AsyncSession) -> None:
    row = (
        await session.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_name='scraper_runs' order by column_name"
            )
        )
    ).all()
    names = {r[0] for r in row}
    assert {"id", "trigger", "status", "started_at", "completed_at",
            "lookback_hours", "pipelines_requested", "stats",
            "error_message"} <= names


@pytest.mark.asyncio
async def test_scraper_runs_status_check_enforced(session: AsyncSession) -> None:
    from uuid import uuid4
    with pytest.raises(Exception):
        await session.execute(
            text(
                "insert into scraper_runs (id, trigger, status, lookback_hours, "
                "pipelines_requested) values (:id, :t, :s, :lb, :p)"
            ),
            {
                "id": str(uuid4()),
                "t": "api",
                "s": "bogus",
                "lb": 24,
                "p": ["youtube"],
            },
        )
        await session.commit()
```

- [ ] **Step 4: Run migrations + test**

Run: `uv run pytest tests/integration/test_scraper_runs_migration.py -v`
Expected: PASS (2 tests). testcontainers-postgres brings up fresh Postgres, runs migrations 0001 + 0002, then the tests validate.

- [ ] **Step 5: Commit**

```bash
git add packages/db/src/news_db/alembic/versions/0002_scraper_runs.py \
        tests/integration/conftest.py \
        tests/integration/test_scraper_runs_migration.py
git commit -m "feat(db): migration 0002 — scraper_runs table"
```

---

### Task 1.4: Add `ScraperRunRepository` (TDD)

**Files:**
- Create: `packages/db/src/news_db/repositories/scraper_run_repo.py`
- Create: `tests/integration/test_scraper_run_repo.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/integration/test_scraper_run_repo.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    RunStats,
    ScraperRunIn,
    ScraperRunStatus,
    YouTubeStats,
)
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_start_creates_running_row(session: AsyncSession) -> None:
    repo = ScraperRunRepository(session)
    row = await repo.start(
        ScraperRunIn(
            trigger="api",
            lookback_hours=24,
            pipelines_requested=[PipelineName.YOUTUBE, PipelineName.RSS],
        )
    )
    assert row.status is ScraperRunStatus.RUNNING
    assert row.completed_at is None
    assert row.pipelines_requested == [PipelineName.YOUTUBE, PipelineName.RSS]


@pytest.mark.asyncio
async def test_complete_sets_status_and_stats(session: AsyncSession) -> None:
    repo = ScraperRunRepository(session)
    started = await repo.start(
        ScraperRunIn(
            trigger="cli",
            lookback_hours=6,
            pipelines_requested=[PipelineName.YOUTUBE],
        )
    )
    stats = RunStats(
        youtube=YouTubeStats(
            status=ScraperRunStatus.SUCCESS, inserted=10, transcripts_fetched=5
        )
    )
    completed = await repo.complete(
        started.id, ScraperRunStatus.SUCCESS, stats
    )
    assert completed.status is ScraperRunStatus.SUCCESS
    assert completed.completed_at is not None
    assert completed.stats.youtube is not None
    assert completed.stats.youtube.inserted == 10


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing(session: AsyncSession) -> None:
    from uuid import uuid4
    repo = ScraperRunRepository(session)
    assert await repo.get_by_id(uuid4()) is None


@pytest.mark.asyncio
async def test_get_recent_returns_newest_first(session: AsyncSession) -> None:
    repo = ScraperRunRepository(session)
    for _ in range(3):
        await repo.start(
            ScraperRunIn(
                trigger="api",
                lookback_hours=24,
                pipelines_requested=[PipelineName.RSS],
            )
        )
    recent = await repo.get_recent(limit=5)
    assert len(recent) == 3
    # Newest first
    assert recent[0].started_at >= recent[-1].started_at


@pytest.mark.asyncio
async def test_mark_orphaned_flips_stale_running_rows(session: AsyncSession) -> None:
    from sqlalchemy import text
    repo = ScraperRunRepository(session)
    fresh = await repo.start(
        ScraperRunIn(
            trigger="api",
            lookback_hours=24,
            pipelines_requested=[PipelineName.RSS],
        )
    )
    # Age one row artificially
    await session.execute(
        text("update scraper_runs set started_at = now() - interval '3 hours' where id = :id"),
        {"id": str(fresh.id)},
    )
    await session.commit()
    count = await repo.mark_orphaned(older_than=datetime.now(UTC) - timedelta(hours=2))
    assert count == 1
    after = await repo.get_by_id(fresh.id)
    assert after is not None
    assert after.status is ScraperRunStatus.FAILED
    assert after.error_message == "orphaned"
```

- [ ] **Step 2: Run — expect import fail**

Run: `uv run pytest tests/integration/test_scraper_run_repo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_db.repositories.scraper_run_repo'`

- [ ] **Step 3: Implement the repository**

Create `packages/db/src/news_db/repositories/scraper_run_repo.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from news_schemas.scraper_run import (
    PipelineName,
    RunStats,
    ScraperRunIn,
    ScraperRunOut,
    ScraperRunStatus,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.scraper_run import ScraperRun


class ScraperRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, run_in: ScraperRunIn) -> ScraperRunOut:
        row = ScraperRun(
            trigger=run_in.trigger,
            status=ScraperRunStatus.RUNNING.value,
            lookback_hours=run_in.lookback_hours,
            pipelines_requested=[p.value for p in run_in.pipelines_requested],
            stats={},
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_out(row)

    async def complete(
        self,
        run_id: UUID,
        status: ScraperRunStatus,
        stats: RunStats,
        error_message: str | None = None,
    ) -> ScraperRunOut:
        stmt = (
            update(ScraperRun)
            .where(ScraperRun.id == run_id)
            .values(
                status=status.value,
                completed_at=datetime.now(UTC),
                stats=stats.model_dump(mode="json"),
                error_message=error_message,
            )
            .returning(ScraperRun)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        await self._session.commit()
        return self._to_out(row)

    async def get_by_id(self, run_id: UUID) -> ScraperRunOut | None:
        row = await self._session.get(ScraperRun, run_id)
        return self._to_out(row) if row else None

    async def get_recent(self, limit: int = 20) -> list[ScraperRunOut]:
        stmt = select(ScraperRun).order_by(ScraperRun.started_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_out(r) for r in rows]

    async def mark_orphaned(self, older_than: datetime) -> int:
        stmt = (
            update(ScraperRun)
            .where(ScraperRun.status == ScraperRunStatus.RUNNING.value)
            .where(ScraperRun.started_at < older_than)
            .values(
                status=ScraperRunStatus.FAILED.value,
                completed_at=datetime.now(UTC),
                error_message="orphaned",
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount or 0

    @staticmethod
    def _to_out(row: ScraperRun) -> ScraperRunOut:
        return ScraperRunOut(
            id=row.id,
            trigger=row.trigger,
            status=ScraperRunStatus(row.status),
            started_at=row.started_at,
            completed_at=row.completed_at,
            lookback_hours=row.lookback_hours,
            pipelines_requested=[PipelineName(p) for p in row.pipelines_requested],
            stats=RunStats.model_validate(row.stats),
            error_message=row.error_message,
        )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/integration/test_scraper_run_repo.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/db/src/news_db/repositories/scraper_run_repo.py \
        tests/integration/test_scraper_run_repo.py
git commit -m "feat(db): add ScraperRunRepository with lifecycle + orphan sweep"
```

---

## Phase 2 — LLM cost tracking in `news_observability.costs`

### Task 2.1: Add `costs.py` with pricing table, `LLMUsage`, `estimate_cost_usd`

**Files:**
- Create: `packages/observability/src/news_observability/costs.py`
- Create: `packages/observability/src/news_observability/tests/test_costs.py`

- [ ] **Step 1: Write failing unit tests**

Create `packages/observability/src/news_observability/tests/test_costs.py`:

```python
from __future__ import annotations

import pytest
from news_observability.costs import LLMUsage, estimate_cost_usd


def test_known_model_returns_expected_cost() -> None:
    # gpt-5.5-mini: $0.15 / 1M input, $0.60 / 1M output
    cost = estimate_cost_usd("gpt-5.5-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(0.75)


def test_small_token_counts_compute_correctly() -> None:
    cost = estimate_cost_usd("gpt-5.5-mini", input_tokens=1000, output_tokens=500)
    assert cost == pytest.approx(0.00015 + 0.0003)


def test_unknown_model_returns_none() -> None:
    cost = estimate_cost_usd("made-up-model-99", input_tokens=1000, output_tokens=1000)
    assert cost is None


def test_zero_tokens_returns_zero() -> None:
    cost = estimate_cost_usd("gpt-5.5-mini", input_tokens=0, output_tokens=0)
    assert cost == pytest.approx(0.0)


def test_llm_usage_dataclass_is_frozen() -> None:
    u = LLMUsage(
        model="gpt-5.5-mini",
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        requests=1,
        estimated_cost_usd=0.01,
    )
    with pytest.raises(AttributeError):
        u.model = "something-else"  # type: ignore[misc]
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest packages/observability/src/news_observability/tests/test_costs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_observability.costs'`

- [ ] **Step 3: Implement `costs.py`**

Create `packages/observability/src/news_observability/costs.py`:

```python
"""LLM usage + cost tracking (OpenAI Agents SDK)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from news_observability.logging import get_logger

if TYPE_CHECKING:
    from agents import RunResult

_log = get_logger("costs")

# Prices per 1M tokens, USD. Update when OpenAI changes pricing.
_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    # model          : (input_per_million, output_per_million)
    "gpt-5.5":        (Decimal("2.50"),  Decimal("10.00")),
    "gpt-5.5-mini":   (Decimal("0.15"),  Decimal("0.60")),
    "gpt-5.5-nano":   (Decimal("0.05"),  Decimal("0.40")),
    "gpt-5.4.1":      (Decimal("2.00"),  Decimal("8.00")),
    "gpt-5.4.1-mini": (Decimal("0.40"),  Decimal("1.60")),
}


@dataclass(frozen=True)
class LLMUsage:
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int
    estimated_cost_usd: float | None


def estimate_cost_usd(
    model: str, *, input_tokens: int, output_tokens: int
) -> float | None:
    """Return estimated USD cost, or None when pricing for *model* is unknown."""
    pricing = _PRICING.get(model)
    if pricing is None:
        _log.warning("unknown model for cost estimate: {}", model)
        return None
    price_in, price_out = pricing
    cost = (Decimal(input_tokens) / Decimal(1_000_000)) * price_in + (
        Decimal(output_tokens) / Decimal(1_000_000)
    ) * price_out
    return float(cost)


def extract_usage(result: "RunResult", *, model: str) -> LLMUsage:
    """Build an LLMUsage from an OpenAI Agents SDK RunResult.

    Uses `result.context_wrapper.usage` as documented in
    https://openai.github.io/openai-agents-python/.
    """
    u = result.context_wrapper.usage
    return LLMUsage(
        model=model,
        input_tokens=u.input_tokens,
        output_tokens=u.output_tokens,
        total_tokens=u.total_tokens,
        requests=u.requests,
        estimated_cost_usd=estimate_cost_usd(
            model, input_tokens=u.input_tokens, output_tokens=u.output_tokens
        ),
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest packages/observability/src/news_observability/tests/test_costs.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/observability/src/news_observability/costs.py \
        packages/observability/src/news_observability/tests/test_costs.py
git commit -m "feat(observability): add costs module (pricing + LLMUsage + extract_usage)"
```

---

### Task 2.2: Test `extract_usage` against a stub `RunResult`

**Files:**
- Modify: `packages/observability/src/news_observability/tests/test_costs.py`

- [ ] **Step 1: Append test for extract_usage**

Append to `packages/observability/src/news_observability/tests/test_costs.py`:

```python
def test_extract_usage_reads_context_wrapper() -> None:
    """Stub RunResult matching the Agents SDK shape."""
    from dataclasses import dataclass
    from news_observability.costs import extract_usage

    @dataclass
    class _Usage:
        input_tokens: int
        output_tokens: int
        total_tokens: int
        requests: int

    @dataclass
    class _Wrapper:
        usage: _Usage

    @dataclass
    class _Result:
        context_wrapper: _Wrapper

    result = _Result(
        context_wrapper=_Wrapper(
            usage=_Usage(
                input_tokens=120, output_tokens=80, total_tokens=200, requests=3
            )
        )
    )
    usage = extract_usage(result, model="gpt-5.5-mini")  # type: ignore[arg-type]
    assert usage.input_tokens == 120
    assert usage.requests == 3
    assert usage.estimated_cost_usd is not None
    assert usage.estimated_cost_usd > 0
```

- [ ] **Step 2: Run — expect pass**

Run: `uv run pytest packages/observability/src/news_observability/tests/test_costs.py::test_extract_usage_reads_context_wrapper -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add packages/observability/src/news_observability/tests/test_costs.py
git commit -m "test(observability): extract_usage against stub RunResult"
```

---

## Phase 3 — Config: sources.yml additions + loader schemas

### Task 3.1: Extend `sources.yml` with `rss:` and `web_search:` blocks

**Files:**
- Modify: `packages/config/src/news_config/sources.yml`

- [ ] **Step 1: Append blocks**

Append to `packages/config/src/news_config/sources.yml` (below existing content, preserving the existing YouTube / `openai:` / `anthropic:` blocks):

```yaml

# --------------------------------------------------------------------
# RSS — blog feeds fetched via rss-mcp (Node MCP server) over stdio.
# --------------------------------------------------------------------
rss:
  enabled: true
  max_concurrent_feeds: 5
  mcp_timeout_seconds: 60
  feeds:
    - name: aws_blog
      url: https://feeds.feedburner.com/AmazonWebServicesBlog
    - name: aws_bigdata
      url: https://blogs.aws.amazon.com/bigdata/blog/feed/recentPosts.rss
    - name: aws_compute
      url: https://aws.amazon.com/blogs/compute/feed/
    - name: aws_security
      url: http://blogs.aws.amazon.com/security/blog/feed/recentPosts.rss
    - name: aws_devops
      url: https://blogs.aws.amazon.com/application-management/blog/feed/recentPosts.rss
    - name: openai_news
      url: https://openai.com/news/rss.xml
    - name: anthropic_news
      url: https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml
    - name: anthropic_engineering
      url: https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_engineering.xml
    - name: anthropic_research
      url: https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml
    - name: anthropic_red_team
      url: https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_red.xml
    - name: gemini_releases
      url: https://cloud.google.com/feeds/gemini-release-notes.xml
    - name: dev_to
      url: https://dev.to/feed
    - name: freecodecamp
      url: https://www.freecodecamp.org/news/rss
    - name: google_devs
      url: https://feeds.feedburner.com/GDBcode
    - name: sitepoint
      url: https://www.sitepoint.com/sitepoint.rss
    - name: sd_times
      url: https://sdtimes.com/feed/
    - name: real_python
      url: https://realpython.com/atom.xml?format=xml
    - name: real_python_podcast
      url: https://realpython.com/podcasts/rpp/feed?sfnsn=mo

# --------------------------------------------------------------------
# Web search — curated sites without reliable RSS, crawled by the
# Playwright MCP + OpenAI Agents SDK agent.
# --------------------------------------------------------------------
web_search:
  enabled: true
  lookback_hours: 48
  max_concurrent_sites: 2
  sites:
    - name: replit_blog
      url: https://replit.com/blog
      list_selector_hint: "Find recent posts listed on this blog page"
    - name: cursor_blog
      url: https://cursor.com/blog
      list_selector_hint: "Find recent posts listed on this blog page"
    - name: huggingface_blog
      url: https://huggingface.co/blog
      list_selector_hint: "Find recent posts listed on this blog page"
```

- [ ] **Step 2: Quick YAML sanity check**

Run: `uv run python -c "import yaml; d = yaml.safe_load(open('packages/config/src/news_config/sources.yml')); print(list(d.keys()))"`
Expected output contains `rss` and `web_search`.

- [ ] **Step 3: Commit**

```bash
git add packages/config/src/news_config/sources.yml
git commit -m "feat(config): add rss and web_search sections to sources.yml"
```

---

### Task 3.2: Extend the loader with Pydantic-validated config

**Files:**
- Modify: `packages/config/src/news_config/loader.py`
- Create: `packages/config/src/news_config/tests/test_loader_rss_websearch.py`

- [ ] **Step 1: Write failing tests**

Create `packages/config/src/news_config/tests/test_loader_rss_websearch.py`:

```python
from __future__ import annotations

from news_config.loader import load_sources


def test_load_sources_reads_rss_block() -> None:
    cfg = load_sources()
    assert cfg.rss is not None
    assert cfg.rss.enabled is True
    assert cfg.rss.max_concurrent_feeds == 5
    names = [f.name for f in cfg.rss.feeds]
    assert "openai_news" in names
    assert "anthropic_engineering" in names


def test_load_sources_reads_web_search_block() -> None:
    cfg = load_sources()
    assert cfg.web_search is not None
    assert cfg.web_search.enabled is True
    assert cfg.web_search.max_concurrent_sites == 2
    site_names = [s.name for s in cfg.web_search.sites]
    assert "replit_blog" in site_names
    for s in cfg.web_search.sites:
        assert str(s.url).startswith("http")


def test_load_sources_backward_compat_fields_still_present() -> None:
    cfg = load_sources()
    assert cfg.youtube_enabled is True
    assert cfg.openai_enabled is True
    assert cfg.anthropic_enabled is True
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest packages/config/src/news_config/tests/test_loader_rss_websearch.py -v`
Expected: FAIL — `AttributeError: 'SourcesConfig' object has no attribute 'rss'`

- [ ] **Step 3: Extend `loader.py`**

Replace the contents of `packages/config/src/news_config/loader.py` with:

```python
"""YAML loader: sources.yml (scraper config) and user_profile.yml (seed user)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from news_schemas.user_profile import UserProfile
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

_PKG_DIR = Path(__file__).parent


class RSSFeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    url: HttpUrl


class RSSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    max_concurrent_feeds: int = 5
    mcp_timeout_seconds: int = 60
    feeds: list[RSSFeedConfig] = Field(default_factory=list)


class WebSearchSiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    url: HttpUrl
    list_selector_hint: str = "Find recent posts listed on this blog page"


class WebSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    lookback_hours: int = 48
    max_concurrent_sites: int = 2
    sites: list[WebSearchSiteConfig] = Field(default_factory=list)


@dataclass(frozen=True)
class SourcesConfig:
    default_hours: int
    youtube_enabled: bool
    youtube_channels: list[dict[str, str]] = field(default_factory=list)
    openai_enabled: bool = False
    anthropic_enabled: bool = False
    anthropic_feed_types: list[str] = field(default_factory=list)
    rss: RSSConfig | None = None
    web_search: WebSearchConfig | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def load_sources(path: Path | None = None) -> SourcesConfig:
    path = path or (_PKG_DIR / "sources.yml")
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    yt = data.get("youtube", {})
    oa = data.get("openai", {})
    an = data.get("anthropic", {})

    rss_cfg = RSSConfig.model_validate(data["rss"]) if "rss" in data else None
    ws_cfg = (
        WebSearchConfig.model_validate(data["web_search"])
        if "web_search" in data
        else None
    )

    return SourcesConfig(
        default_hours=int(data.get("default_hours", 24)),
        youtube_enabled=bool(yt.get("enabled", False)),
        youtube_channels=list(yt.get("channels", [])),
        openai_enabled=bool(oa.get("enabled", False)),
        anthropic_enabled=bool(an.get("enabled", False)),
        anthropic_feed_types=list(an.get("feed_types", [])),
        rss=rss_cfg,
        web_search=ws_cfg,
        raw=data,
    )


def load_user_profile_yaml(
    path: Path | None = None,
) -> tuple[UserProfile, dict[str, str]]:
    """Return (validated UserProfile, identity-level fields {name, email_name})."""
    path = path or (_PKG_DIR / "user_profile.yml")
    data = yaml.safe_load(path.read_text())
    user = data["user"]
    identity = {"name": user["name"], "email_name": user["email_name"]}
    profile_dict = {
        "background": user.get("background", []),
        "interests": user["interests"],
        "preferences": user["preferences"],
        "goals": user["goals"],
        "reading_time": user["reading_time"],
    }
    return UserProfile.model_validate(profile_dict), identity
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest packages/config/src/news_config/tests/test_loader_rss_websearch.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/config/src/news_config/loader.py \
        packages/config/src/news_config/tests/test_loader_rss_websearch.py
git commit -m "feat(config): validate rss and web_search sections via Pydantic loader"
```

---

### Task 3.3: Add `OPENAI_MODEL` to `OpenAISettings`

**Files:**
- Modify: `packages/config/src/news_config/settings.py`
- Create: `packages/config/src/news_config/tests/test_settings_openai_model.py`

- [ ] **Step 1: Write failing test**

Create `packages/config/src/news_config/tests/test_settings_openai_model.py`:

```python
from __future__ import annotations

import os

from news_config.settings import OpenAISettings


def test_model_defaults_to_gpt_5_5_mini(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    s = OpenAISettings()
    assert s.model == "gpt-5.5-mini"


def test_model_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.5")
    s = OpenAISettings()
    assert s.model == "gpt-5.5"
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest packages/config/src/news_config/tests/test_settings_openai_model.py -v`
Expected: FAIL — `AttributeError: 'OpenAISettings' object has no attribute 'model'`

- [ ] **Step 3: Add `model` field**

Edit `packages/config/src/news_config/settings.py`; replace the `OpenAISettings` class with:

```python
class OpenAISettings(_Base):
    api_key: str = Field(default="", alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-5.5-mini", alias="OPENAI_MODEL")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest packages/config/src/news_config/tests/test_settings_openai_model.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/config/src/news_config/settings.py \
        packages/config/src/news_config/tests/test_settings_openai_model.py
git commit -m "feat(config): add OPENAI_MODEL to OpenAISettings (default gpt-5.5-mini)"
```

---

## Phase 4 — `services/scraper/` workspace scaffold

### Task 4.1: Create the scraper workspace member

**Files:**
- Create: `services/scraper/pyproject.toml`
- Create: `services/scraper/src/news_scraper/__init__.py`
- Create: `services/scraper/src/news_scraper/tests/__init__.py`
- Create: `services/scraper/src/news_scraper/tests/unit/__init__.py`
- Modify: `pyproject.toml` (root — add workspace member)
- Modify: `mypy.ini` (add scraper to mypy_path, exclude _legacy)
- Modify: `.pre-commit-config.yaml` (expand mypy `files` to include scraper src)
- Modify: `ruff.toml` (already excludes `_legacy` — no change but confirm)

- [ ] **Step 1: Create the scraper `pyproject.toml`**

Create `services/scraper/pyproject.toml`:

```toml
[project]
name = "news_scraper"
version = "0.1.0"
requires-python = ">=3.12"
description = "Ingestion service — YouTube RSS, blog RSS, web search"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "typer>=0.12",
    "feedparser>=6.0.11",
    "youtube-transcript-api>=0.6.2",
    "python-dateutil>=2.9",
    "openai-agents>=0.14.5",
    "pydantic>=2.13.3",
    "pydantic-settings>=2.5",
    "loguru>=0.7.3",
    "news_schemas",
    "news_config",
    "news_observability",
    "news_db",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/news_scraper"]
```

- [ ] **Step 2: Create empty package + test `__init__.py` files**

Create `services/scraper/src/news_scraper/__init__.py`:

```python
"""News Scraper — ingestion service."""

__version__ = "0.1.0"
```

Create `services/scraper/src/news_scraper/tests/__init__.py` (empty file):

```python
```

Create `services/scraper/src/news_scraper/tests/unit/__init__.py` (empty file):

```python
```

- [ ] **Step 3: Add scraper to root workspace**

Edit `pyproject.toml` (root); replace the `[tool.uv.workspace]` and `[tool.uv.sources]` blocks with:

```toml
[tool.uv.workspace]
members = [
    "packages/schemas",
    "packages/config",
    "packages/observability",
    "packages/db",
    "services/scraper",
]

[tool.uv.sources]
news_schemas = { workspace = true }
news_config = { workspace = true }
news_observability = { workspace = true }
news_db = { workspace = true }
news_scraper = { workspace = true }
```

- [ ] **Step 4: Update mypy.ini**

Edit `mypy.ini`; replace the `mypy_path` line with:

```
mypy_path = packages/schemas/src:packages/config/src:packages/observability/src:packages/db/src:services/scraper/src
```

And append these ignore blocks at the end:

```
[mypy-agents.*]
ignore_missing_imports = True

[mypy-typer.*]
ignore_missing_imports = True

[mypy-fastapi.*]
ignore_missing_imports = True

[mypy-uvicorn.*]
ignore_missing_imports = True

[mypy-dateutil.*]
ignore_missing_imports = True

[mypy-feedparser.*]
ignore_missing_imports = True
```

(Note: `feedparser` is already there — keep the single block.)

- [ ] **Step 5: Update .pre-commit-config.yaml**

Edit `.pre-commit-config.yaml`; replace the `files:` line under mypy hook with:

```yaml
        files: ^(packages/.*/src/.*\.py$|services/scraper/src/.*\.py$)
```

And extend `additional_dependencies` to include FastAPI/Typer so mypy resolves imports:

```yaml
        additional_dependencies:
          - pydantic>=2.13
          - pydantic-settings>=2.5
          - sqlalchemy>=2.0.36
          - types-PyYAML
          - fastapi>=0.115
          - typer>=0.12
```

- [ ] **Step 6: Run `uv sync --all-packages` and verify**

Run: `uv sync --all-packages`
Expected: `news_scraper` gets installed into `.venv`.

Run: `uv run python -c "import news_scraper; print(news_scraper.__version__)"`
Expected output: `0.1.0`

- [ ] **Step 7: Run full check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy packages services/scraper/src`
Expected: all pass (no type errors yet since there's no code).

- [ ] **Step 8: Commit**

```bash
git add services/scraper/pyproject.toml \
        services/scraper/src/news_scraper/__init__.py \
        services/scraper/src/news_scraper/tests \
        pyproject.toml mypy.ini .pre-commit-config.yaml
git commit -m "feat(scraper): scaffold services/scraper uv workspace member"
```

---

### Task 4.2: Add `ScraperSettings`

**Files:**
- Create: `services/scraper/src/news_scraper/settings.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_settings.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_settings.py`:

```python
from __future__ import annotations

import pytest
from news_scraper.settings import ScraperSettings


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "RSS_MCP_PATH",
        "WEB_SEARCH_MAX_TURNS",
        "WEB_SEARCH_SITE_TIMEOUT",
        "YOUTUBE_TRANSCRIPT_CONCURRENCY",
        "RSS_FEED_CONCURRENCY",
        "WEB_SEARCH_SITE_CONCURRENCY",
    ):
        monkeypatch.delenv(k, raising=False)
    s = ScraperSettings()
    assert s.rss_mcp_path == "/app/rss-mcp/dist/index.js"
    assert s.web_search_max_turns == 15
    assert s.web_search_site_timeout == 120
    assert s.youtube_transcript_concurrency == 3
    assert s.rss_feed_concurrency == 5
    assert s.web_search_site_concurrency == 2


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RSS_FEED_CONCURRENCY", "10")
    monkeypatch.setenv("WEB_SEARCH_MAX_TURNS", "8")
    s = ScraperSettings()
    assert s.rss_feed_concurrency == 10
    assert s.web_search_max_turns == 8
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_settings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.settings'`

- [ ] **Step 3: Implement settings**

Create `services/scraper/src/news_scraper/settings.py`:

```python
"""Scraper-specific settings, extending the AppSettings baseline."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScraperSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    rss_mcp_path: str = Field(
        default="/app/rss-mcp/dist/index.js", alias="RSS_MCP_PATH"
    )
    web_search_max_turns: int = Field(default=15, alias="WEB_SEARCH_MAX_TURNS")
    web_search_site_timeout: int = Field(
        default=120, alias="WEB_SEARCH_SITE_TIMEOUT"
    )
    youtube_transcript_concurrency: int = Field(
        default=3, alias="YOUTUBE_TRANSCRIPT_CONCURRENCY"
    )
    rss_feed_concurrency: int = Field(default=5, alias="RSS_FEED_CONCURRENCY")
    web_search_site_concurrency: int = Field(
        default=2, alias="WEB_SEARCH_SITE_CONCURRENCY"
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_settings.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/settings.py \
        services/scraper/src/news_scraper/tests/unit/test_settings.py
git commit -m "feat(scraper): add ScraperSettings (rss_mcp_path, concurrency, timeouts)"
```

---

### Task 4.3: Add `stats.py` — `merge_stats` + `compute_run_status`

**Files:**
- Create: `services/scraper/src/news_scraper/stats.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_stats.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_stats.py`:

```python
from __future__ import annotations

from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    ScraperRunStatus,
    WebSearchStats,
    YouTubeStats,
)
from news_scraper.stats import compute_run_status, merge_pipeline_results


def test_compute_status_all_success() -> None:
    stats_map: dict[PipelineName, PipelineStats] = {
        PipelineName.RSS: PipelineStats(status=ScraperRunStatus.SUCCESS),
        PipelineName.YOUTUBE: YouTubeStats(status=ScraperRunStatus.SUCCESS),
    }
    assert compute_run_status(stats_map) is ScraperRunStatus.SUCCESS


def test_compute_status_all_failed() -> None:
    stats_map: dict[PipelineName, PipelineStats] = {
        PipelineName.RSS: PipelineStats(status=ScraperRunStatus.FAILED),
        PipelineName.YOUTUBE: YouTubeStats(status=ScraperRunStatus.FAILED),
    }
    assert compute_run_status(stats_map) is ScraperRunStatus.FAILED


def test_compute_status_mixed_is_partial() -> None:
    stats_map: dict[PipelineName, PipelineStats] = {
        PipelineName.RSS: PipelineStats(status=ScraperRunStatus.SUCCESS),
        PipelineName.YOUTUBE: YouTubeStats(status=ScraperRunStatus.FAILED),
    }
    assert compute_run_status(stats_map) is ScraperRunStatus.PARTIAL


def test_compute_status_empty_is_failed() -> None:
    assert compute_run_status({}) is ScraperRunStatus.FAILED


def test_merge_pipeline_results_pairs_by_name() -> None:
    youtube = YouTubeStats(status=ScraperRunStatus.SUCCESS, inserted=2)
    rss = PipelineStats(status=ScraperRunStatus.SUCCESS, inserted=3)
    web = WebSearchStats(status=ScraperRunStatus.PARTIAL, sites_attempted=2)
    merged = merge_pipeline_results(
        {
            PipelineName.YOUTUBE: youtube,
            PipelineName.RSS: rss,
            PipelineName.WEB_SEARCH: web,
        }
    )
    assert merged.youtube is youtube
    assert merged.rss is rss
    assert merged.web_search is web
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.stats'`

- [ ] **Step 3: Implement stats**

Create `services/scraper/src/news_scraper/stats.py`:

```python
"""Helpers for computing run-level status and merging per-pipeline stats."""

from __future__ import annotations

from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    RunStats,
    ScraperRunStatus,
    WebSearchStats,
    YouTubeStats,
)


def compute_run_status(
    stats_map: dict[PipelineName, PipelineStats],
) -> ScraperRunStatus:
    """success iff ALL pipelines succeed; failed iff ALL fail; else partial.

    Empty map => failed (caller should treat "nothing ran" as failure).
    """
    if not stats_map:
        return ScraperRunStatus.FAILED
    statuses = [s.status for s in stats_map.values()]
    if all(s is ScraperRunStatus.SUCCESS for s in statuses):
        return ScraperRunStatus.SUCCESS
    if all(s is ScraperRunStatus.FAILED for s in statuses):
        return ScraperRunStatus.FAILED
    return ScraperRunStatus.PARTIAL


def merge_pipeline_results(
    stats_map: dict[PipelineName, PipelineStats],
) -> RunStats:
    """Build a RunStats from pipeline → stats mapping."""
    youtube = stats_map.get(PipelineName.YOUTUBE)
    rss = stats_map.get(PipelineName.RSS)
    web = stats_map.get(PipelineName.WEB_SEARCH)
    return RunStats(
        youtube=youtube if isinstance(youtube, YouTubeStats) else None,
        rss=rss,
        web_search=web if isinstance(web, WebSearchStats) else None,
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_stats.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/stats.py \
        services/scraper/src/news_scraper/tests/unit/test_stats.py
git commit -m "feat(scraper): add stats helpers (compute_run_status, merge_pipeline_results)"
```

---

## Phase 5 — Adapters: protocols, MCP factories, production impls

### Task 5.1: Define Pipeline base + adapter protocols + value types

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/__init__.py`
- Create: `services/scraper/src/news_scraper/pipelines/base.py`
- Create: `services/scraper/src/news_scraper/pipelines/adapters.py`

- [ ] **Step 1: Create the pipelines package**

Create `services/scraper/src/news_scraper/pipelines/__init__.py` (empty):

```python
```

- [ ] **Step 2: Create `base.py` with the Pipeline Protocol**

Create `services/scraper/src/news_scraper/pipelines/base.py`:

```python
"""Pipeline Protocol shared by the three source pipelines."""

from __future__ import annotations

from typing import Protocol

from news_schemas.scraper_run import PipelineName, PipelineStats


class Pipeline(Protocol):
    name: PipelineName

    async def run(self, *, lookback_hours: int) -> PipelineStats: ...
```

- [ ] **Step 3: Create `adapters.py` with all protocols and value types**

Create `services/scraper/src/news_scraper/pipelines/adapters.py`:

```python
"""Adapter boundaries — every MCP/network call goes through these Protocols.

Unit tests inject fakes; production wires the MCP/feedparser-backed impls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from news_config.loader import WebSearchSiteConfig
from pydantic import BaseModel, Field, HttpUrl


# -------- YouTube adapter types --------

@dataclass(frozen=True)
class VideoMetadata:
    video_id: str
    title: str
    url: str
    channel_id: str
    published_at: datetime | None
    description: str
    thumbnail_url: str | None


@dataclass(frozen=True)
class FetchedTranscript:
    text: str | None
    segments: list[dict[str, Any]] | None
    error: str | None


class YouTubeFeedFetcher(Protocol):
    async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]: ...


class TranscriptFetcher(Protocol):
    async def fetch(
        self, video_id: str, languages: list[str] | None = None
    ) -> FetchedTranscript: ...


# -------- RSS adapter --------

class FeedFetcher(Protocol):
    async def get_feed(self, url: str, count: int = 15) -> dict[str, Any]: ...


# -------- Web-search adapter types --------

class WebSearchItem(BaseModel):
    title: str = Field(..., min_length=1)
    url: HttpUrl
    author: str | None = None
    published_at: datetime | None = None
    summary: str | None = Field(default=None, max_length=2000)


class SiteCrawlResult(BaseModel):
    site_name: str
    items: list[WebSearchItem] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class CrawlOutcome:
    result: SiteCrawlResult
    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int
    cost_usd: float | None
    duration_ms: int


class WebCrawler(Protocol):
    async def crawl_site(
        self, site: WebSearchSiteConfig, *, lookback_hours: int
    ) -> CrawlOutcome: ...
```

- [ ] **Step 4: Smoke import**

Run: `uv run python -c "from news_scraper.pipelines.adapters import SiteCrawlResult, WebSearchItem; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/__init__.py \
        services/scraper/src/news_scraper/pipelines/base.py \
        services/scraper/src/news_scraper/pipelines/adapters.py
git commit -m "feat(scraper): pipeline Protocol + adapter Protocols and value types"
```

---

### Task 5.2: Add `mcp_servers.py` — factories for rss-mcp and Playwright MCP

**Files:**
- Create: `services/scraper/src/news_scraper/mcp_servers.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_mcp_servers.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_mcp_servers.py`:

```python
from __future__ import annotations

from news_scraper.mcp_servers import (
    _playwright_args,
    _rss_mcp_params,
)


def test_rss_mcp_params_builds_node_command(tmp_path) -> None:
    fake = tmp_path / "index.js"
    fake.write_text("// stub")
    params = _rss_mcp_params(str(fake))
    assert params["command"] == "node"
    assert params["args"] == [str(fake)]


def test_playwright_args_contain_hardening_flags() -> None:
    args = _playwright_args(docker=False)
    assert "--headless" in args
    assert "--isolated" in args
    assert "--no-sandbox" in args
    assert "--ignore-https-errors" in args
    assert "--user-agent" in args


def test_playwright_args_in_docker_add_executable_path(tmp_path, monkeypatch) -> None:
    # Fake a discovered chrome path. We don't need a real file.
    chrome_dir = tmp_path / "ms-playwright" / "chromium-9999" / "chrome-linux"
    chrome_dir.mkdir(parents=True)
    chrome = chrome_dir / "chrome"
    chrome.write_text("#!/bin/bash")
    monkeypatch.setattr(
        "news_scraper.mcp_servers._find_chromium",
        lambda: str(chrome),
    )
    args = _playwright_args(docker=True)
    assert "--executable-path" in args
    i = args.index("--executable-path")
    assert args[i + 1] == str(chrome)
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_mcp_servers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.mcp_servers'`

- [ ] **Step 3: Implement `mcp_servers.py`**

Create `services/scraper/src/news_scraper/mcp_servers.py`:

```python
"""MCP server factory functions.

Pattern follows alex-multi-agent-saas/backend/researcher/mcp_servers.py.
Returns configured MCPServerStdio instances ready for `async with` usage.
"""

from __future__ import annotations

import glob
import os
from typing import Any

from agents.mcp import MCPServerStdio

_PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def _rss_mcp_params(path: str) -> dict[str, Any]:
    return {"command": "node", "args": [path]}


def _find_chromium() -> str | None:
    paths = glob.glob(
        "/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"
    )
    return paths[0] if paths else None


def _in_docker() -> bool:
    return os.path.exists("/.dockerenv") or bool(os.environ.get("AWS_EXECUTION_ENV"))


def _playwright_args(*, docker: bool) -> list[str]:
    args: list[str] = [
        "@playwright/mcp@latest",
        "--headless",
        "--isolated",
        "--no-sandbox",
        "--ignore-https-errors",
        "--user-agent",
        _PLAYWRIGHT_USER_AGENT,
    ]
    if docker:
        chrome = _find_chromium()
        if chrome:
            args.extend(["--executable-path", chrome])
        else:
            args.extend(
                [
                    "--executable-path",
                    "/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
                ]
            )
    return args


def create_rss_mcp_server(
    path: str, *, timeout_seconds: int = 60
) -> MCPServerStdio:
    """Spawn rss-mcp (Node) as a stdio MCP server. Use as `async with`.

    path: absolute path to rss-mcp/dist/index.js
    """
    return MCPServerStdio(
        name="rss-mcp",
        params=_rss_mcp_params(path),
        cache_tools_list=True,
        client_session_timeout_seconds=timeout_seconds,
    )


def create_playwright_mcp_server(
    *, timeout_seconds: int = 120
) -> MCPServerStdio:
    """Spawn @playwright/mcp@latest as a stdio MCP server. Use as `async with`."""
    return MCPServerStdio(
        name="playwright-mcp",
        params={"command": "npx", "args": _playwright_args(docker=_in_docker())},
        cache_tools_list=True,
        client_session_timeout_seconds=timeout_seconds,
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_mcp_servers.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/mcp_servers.py \
        services/scraper/src/news_scraper/tests/unit/test_mcp_servers.py
git commit -m "feat(scraper): MCP server factories (rss-mcp + playwright)"
```

---

### Task 5.3: Implement `FeedparserYouTubeFeedFetcher`

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/youtube_adapters.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py`:

```python
from __future__ import annotations

import types
from datetime import datetime, timezone

import pytest
from news_scraper.pipelines.youtube_adapters import FeedparserYouTubeFeedFetcher


def _fake_parse_factory(entries: list[dict]):
    def _fake_parse(url: str):
        return types.SimpleNamespace(
            bozo=False, bozo_exception=None, entries=[
                types.SimpleNamespace(**e) for e in entries
            ]
        )
    return _fake_parse


@pytest.mark.asyncio
async def test_list_recent_videos_parses_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_parse = _fake_parse_factory(
        [
            {
                "id": "yt:video:abc123",
                "title": "Hello",
                "link": "https://www.youtube.com/watch?v=abc123",
                "published_parsed": (2026, 4, 24, 10, 0, 0, 0, 0, 0),
                "summary": "desc",
            }
        ]
    )
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.feedparser.parse",
        fake_parse,
    )
    fetcher = FeedparserYouTubeFeedFetcher()
    videos = await fetcher.list_recent_videos("UC_test")
    assert len(videos) == 1
    assert videos[0].video_id == "abc123"
    assert videos[0].published_at == datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)
    assert videos[0].channel_id == "UC_test"


@pytest.mark.asyncio
async def test_list_recent_videos_handles_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_parse = _fake_parse_factory(
        [{"id": "yt:video:xyz", "title": "t", "link": "https://u"}]
    )
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.feedparser.parse",
        fake_parse,
    )
    fetcher = FeedparserYouTubeFeedFetcher()
    videos = await fetcher.list_recent_videos("UC_test")
    assert videos[0].video_id == "xyz"
    assert videos[0].published_at is None
    assert videos[0].description == ""


@pytest.mark.asyncio
async def test_empty_feed_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.feedparser.parse",
        _fake_parse_factory([]),
    )
    fetcher = FeedparserYouTubeFeedFetcher()
    assert await fetcher.list_recent_videos("UC_test") == []
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.pipelines.youtube_adapters'`

- [ ] **Step 3: Implement the fetcher**

Create `services/scraper/src/news_scraper/pipelines/youtube_adapters.py`:

```python
"""Production adapters for the YouTube pipeline."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import feedparser
from news_observability.logging import get_logger

from news_scraper.pipelines.adapters import VideoMetadata

_log = get_logger("youtube_adapter")

_RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


class FeedparserYouTubeFeedFetcher:
    async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]:
        url = _RSS_URL_TEMPLATE.format(channel_id=channel_id)
        feed: Any = await asyncio.to_thread(feedparser.parse, url)
        if getattr(feed, "bozo", False):
            _log.warning(
                "feed parse bozo for {}: {}", channel_id, feed.bozo_exception
            )
        return [self._parse_entry(e, channel_id) for e in feed.entries]

    @staticmethod
    def _parse_entry(entry: Any, channel_id: str) -> VideoMetadata:
        entry_id = getattr(entry, "id", None) or ""
        video_id = entry_id.split(":")[-1] if entry_id else ""
        pub = getattr(entry, "published_parsed", None)
        published_at = (
            datetime(*pub[:6], tzinfo=timezone.utc) if pub else None
        )
        description = getattr(entry, "summary", "") or ""
        thumbnail_url = None
        media_thumbnail = getattr(entry, "media_thumbnail", None)
        if media_thumbnail:
            thumbnail_url = media_thumbnail[0].get("url")
        return VideoMetadata(
            video_id=video_id,
            title=getattr(entry, "title", "") or "",
            url=getattr(entry, "link", "") or "",
            channel_id=channel_id,
            published_at=published_at,
            description=description,
            thumbnail_url=thumbnail_url,
        )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/youtube_adapters.py \
        services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py
git commit -m "feat(scraper): FeedparserYouTubeFeedFetcher (async wrapper over feedparser)"
```

---

### Task 5.4: Implement `YouTubeTranscriptApiFetcher` with Webshare fallback

**Files:**
- Modify: `services/scraper/src/news_scraper/pipelines/youtube_adapters.py`
- Modify: `services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py`

- [ ] **Step 1: Append failing tests**

Append to `services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py`:

```python
@pytest.mark.asyncio
async def test_transcript_fetcher_returns_text_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scraper.pipelines.youtube_adapters import YouTubeTranscriptApiFetcher

    class _FakeAPI:
        def __init__(self, proxy_config=None) -> None: ...
        def fetch(self, video_id, languages):
            return types.SimpleNamespace(
                to_raw_data=lambda: [{"text": "hi", "start": 0.0, "duration": 1.0}]
            )

    def _fake_format(transcript):
        return "hi"

    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.YouTubeTranscriptApi", _FakeAPI
    )
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.TextFormatter",
        lambda: types.SimpleNamespace(format_transcript=_fake_format),
    )
    fetcher = YouTubeTranscriptApiFetcher(proxy_enabled=False)
    result = await fetcher.fetch("abc123")
    assert result.text == "hi"
    assert result.segments == [{"text": "hi", "start": 0.0, "duration": 1.0}]
    assert result.error is None


@pytest.mark.asyncio
async def test_transcript_fetcher_graceful_degradation_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scraper.pipelines.youtube_adapters import YouTubeTranscriptApiFetcher

    class _FakeAPI:
        def __init__(self, proxy_config=None) -> None: ...
        def fetch(self, video_id, languages):
            raise RuntimeError("YouTube is blocking requests")

    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.YouTubeTranscriptApi", _FakeAPI
    )
    fetcher = YouTubeTranscriptApiFetcher(proxy_enabled=False)
    result = await fetcher.fetch("abc")
    assert result.text is None
    assert result.error is not None
    assert "blocking" in result.error.lower()
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py::test_transcript_fetcher_returns_text_on_success -v`
Expected: FAIL — `ImportError: cannot import name 'YouTubeTranscriptApiFetcher'`

- [ ] **Step 3: Implement the transcript fetcher**

Append to `services/scraper/src/news_scraper/pipelines/youtube_adapters.py`:

```python
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from news_scraper.pipelines.adapters import FetchedTranscript


class YouTubeTranscriptApiFetcher:
    def __init__(
        self,
        *,
        proxy_enabled: bool,
        proxy_username: str = "",
        proxy_password: str = "",
    ) -> None:
        self._proxy_enabled = proxy_enabled and bool(proxy_username) and bool(
            proxy_password
        )
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password

    async def fetch(
        self, video_id: str, languages: list[str] | None = None
    ) -> FetchedTranscript:
        return await asyncio.to_thread(self._fetch_sync, video_id, languages or ["en"])

    def _fetch_sync(
        self, video_id: str, languages: list[str]
    ) -> FetchedTranscript:
        try:
            api = self._build_api()
            fetched = api.fetch(video_id, languages=languages)
            segments = fetched.to_raw_data()
            full_text = TextFormatter().format_transcript(fetched)
            return FetchedTranscript(
                text=full_text, segments=segments, error=None
            )
        except Exception as exc:  # includes TranscriptsDisabled, NoTranscriptFound, RequestBlocked
            _log.info("transcript fetch failed for {}: {}", video_id, exc)
            return FetchedTranscript(text=None, segments=None, error=str(exc))

    def _build_api(self) -> Any:
        if self._proxy_enabled:
            from youtube_transcript_api.proxies import WebshareProxyConfig
            return YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=self._proxy_username,
                    proxy_password=self._proxy_password,
                )
            )
        return YouTubeTranscriptApi()
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py -v`
Expected: PASS (5 tests total)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/youtube_adapters.py \
        services/scraper/src/news_scraper/tests/unit/test_youtube_adapters.py
git commit -m "feat(scraper): YouTubeTranscriptApiFetcher with Webshare fallback + graceful degradation"
```

---

### Task 5.5: Implement `MCPFeedFetcher` (rss-mcp wrapper)

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/rss_adapters.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_rss_adapters.py`

- [ ] **Step 1: Write failing tests (stub MCP server)**

Create `services/scraper/src/news_scraper/tests/unit/test_rss_adapters.py`:

```python
from __future__ import annotations

import json
import types
from dataclasses import dataclass

import pytest
from news_scraper.pipelines.rss_adapters import MCPFeedFetcher


@dataclass
class _Content:
    text: str


@dataclass
class _ToolResult:
    content: list[_Content]
    isError: bool = False


class _FakeServer:
    async def call_tool(self, name, args):
        payload = {"items": [{"title": "t", "link": "https://x"}]}
        return _ToolResult(content=[_Content(text=json.dumps(payload))])


@pytest.mark.asyncio
async def test_get_feed_returns_dict_from_mcp() -> None:
    fetcher = MCPFeedFetcher(_FakeServer())
    result = await fetcher.get_feed("https://example.com/rss")
    assert result["items"][0]["title"] == "t"


@pytest.mark.asyncio
async def test_get_feed_raises_on_tool_error() -> None:
    class _ErrServer:
        async def call_tool(self, name, args):
            return _ToolResult(content=[_Content(text="boom")], isError=True)

    fetcher = MCPFeedFetcher(_ErrServer())
    with pytest.raises(RuntimeError, match="boom"):
        await fetcher.get_feed("https://example.com/rss")


@pytest.mark.asyncio
async def test_get_feed_raises_on_empty_response() -> None:
    class _EmptyServer:
        async def call_tool(self, name, args):
            return _ToolResult(content=[])

    fetcher = MCPFeedFetcher(_EmptyServer())
    with pytest.raises(ValueError, match="Empty response"):
        await fetcher.get_feed("https://example.com/rss")
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_rss_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.pipelines.rss_adapters'`

- [ ] **Step 3: Implement the adapter**

Create `services/scraper/src/news_scraper/pipelines/rss_adapters.py`:

```python
"""RSS adapter — wraps MCPServerStdio over rss-mcp."""

from __future__ import annotations

import json
from typing import Any, Protocol

from news_observability.logging import get_logger

_log = get_logger("rss_adapter")


class _MCPServer(Protocol):
    async def call_tool(self, name: str, args: dict[str, Any]) -> Any: ...


class MCPFeedFetcher:
    """Thin wrapper around an MCPServerStdio-backed session calling get_feed."""

    def __init__(self, server: _MCPServer) -> None:
        self._server = server

    async def get_feed(self, url: str, count: int = 15) -> dict[str, Any]:
        result = await self._server.call_tool(
            "get_feed", {"url": url, "count": count}
        )
        is_error = getattr(result, "isError", False) or getattr(result, "is_error", False)
        if is_error:
            err = result.content[0].text if result.content else "unknown error"
            raise RuntimeError(f"get_feed error: {err}")
        if not result.content:
            raise ValueError("Empty response from get_feed")
        text = result.content[0].text
        return json.loads(text)  # type: ignore[no-any-return]
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_rss_adapters.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/rss_adapters.py \
        services/scraper/src/news_scraper/tests/unit/test_rss_adapters.py
git commit -m "feat(scraper): MCPFeedFetcher wrapping rss-mcp get_feed tool"
```

---

### Task 5.6: Implement `PlaywrightAgentCrawler`

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/web_search_adapters.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_web_search_adapters.py`

- [ ] **Step 1: Write failing tests (mocking Runner.run)**

Create `services/scraper/src/news_scraper/tests/unit/test_web_search_adapters.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

import pytest
from news_config.loader import WebSearchSiteConfig
from news_scraper.pipelines.adapters import SiteCrawlResult, WebSearchItem
from news_scraper.pipelines.web_search_adapters import PlaywrightAgentCrawler


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 50
    total_tokens: int = 150
    requests: int = 2


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: SiteCrawlResult
    context_wrapper: _Wrapper


@pytest.mark.asyncio
async def test_crawl_site_returns_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result = _FakeResult(
        final_output=SiteCrawlResult(
            site_name="replit_blog",
            items=[
                WebSearchItem(title="Post 1", url="https://replit.com/blog/post-1")
            ],
        ),
        context_wrapper=_Wrapper(usage=_Usage()),
    )

    async def _fake_runner_run(agent, input, max_turns):  # noqa: A002
        return fake_result

    class _FakeMCP:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

    def _fake_factory(*, timeout_seconds):
        return _FakeMCP()

    monkeypatch.setattr(
        "news_scraper.pipelines.web_search_adapters.Runner.run",
        _fake_runner_run,
    )
    monkeypatch.setattr(
        "news_scraper.pipelines.web_search_adapters.create_playwright_mcp_server",
        _fake_factory,
    )

    crawler = PlaywrightAgentCrawler(
        model="gpt-5.5-mini", max_turns=5, site_timeout=30
    )
    site = WebSearchSiteConfig(
        name="replit_blog",
        url="https://replit.com/blog",
        list_selector_hint="Find recent posts listed on this blog page",
    )
    outcome = await crawler.crawl_site(site, lookback_hours=48)
    assert outcome.result.site_name == "replit_blog"
    assert outcome.input_tokens == 100
    assert outcome.total_tokens == 150
    assert outcome.cost_usd is not None
    assert outcome.duration_ms >= 0
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_web_search_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.pipelines.web_search_adapters'`

- [ ] **Step 3: Implement the crawler**

Create `services/scraper/src/news_scraper/pipelines/web_search_adapters.py`:

```python
"""Web-search adapter — Playwright MCP + OpenAI Agents SDK."""

from __future__ import annotations

from time import perf_counter

from agents import Agent, Runner, trace
from news_config.loader import WebSearchSiteConfig
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.sanitizer import sanitize_prompt_input
from news_observability.validators import validate_structured_output

from news_scraper.mcp_servers import create_playwright_mcp_server
from news_scraper.pipelines.adapters import CrawlOutcome, SiteCrawlResult

_log = get_logger("web_search_adapter")


def _build_agent(pw_mcp, *, model: str, lookback_hours: int) -> Agent:
    instructions = (
        "You are a web crawler. You will be given a site URL and instructed to "
        "list recent posts. Use the Playwright browser tools to navigate to the "
        "URL and identify a list of posts. For each post extract:\n"
        "  - title (required)\n"
        "  - url (required, absolute)\n"
        "  - author (if visible, else null)\n"
        "  - published_at (ISO 8601 if visible, else null)\n"
        "  - summary (short excerpt, under 2000 chars)\n"
        f"Include at most 20 items. Return only items from the last {lookback_hours} "
        "hours based on published_at, or include the item if it appears prominently "
        "on the front page when published_at is missing."
    )
    return Agent(
        name="WebSearchCrawler",
        instructions=instructions,
        model=model,
        mcp_servers=[pw_mcp],
        output_type=SiteCrawlResult,
    )


class PlaywrightAgentCrawler:
    def __init__(self, *, model: str, max_turns: int, site_timeout: int) -> None:
        self._model = model
        self._max_turns = max_turns
        self._site_timeout = site_timeout

    async def crawl_site(
        self, site: WebSearchSiteConfig, *, lookback_hours: int
    ) -> CrawlOutcome:
        t0 = perf_counter()
        async with create_playwright_mcp_server(
            timeout_seconds=self._site_timeout
        ) as pw:
            agent = _build_agent(
                pw, model=self._model, lookback_hours=lookback_hours
            )
            safe_hint = sanitize_prompt_input(site.list_selector_hint)
            prompt = f"Visit {site.url} and list recent posts. {safe_hint}"
            with trace(f"web_search.{site.name}"):
                result = await Runner.run(
                    agent, input=prompt, max_turns=self._max_turns
                )
            crawl = validate_structured_output(
                SiteCrawlResult, result.final_output
            )
            usage = extract_usage(result, model=self._model)
            elapsed_ms = int((perf_counter() - t0) * 1000)
            return CrawlOutcome(
                result=crawl,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                requests=usage.requests,
                cost_usd=usage.estimated_cost_usd,
                duration_ms=elapsed_ms,
            )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_web_search_adapters.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/web_search_adapters.py \
        services/scraper/src/news_scraper/tests/unit/test_web_search_adapters.py
git commit -m "feat(scraper): PlaywrightAgentCrawler (Agents SDK + Playwright MCP + usage extraction)"
```

---

## Phase 6 — Pipeline implementations

### Task 6.1: `YouTubePipeline`

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/youtube.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_pipelines_youtube.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_pipelines_youtube.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from news_schemas.article import ArticleIn
from news_schemas.scraper_run import ScraperRunStatus
from news_scraper.pipelines.adapters import FetchedTranscript, VideoMetadata
from news_scraper.pipelines.youtube import YouTubePipeline


class _FakeFeedFetcher:
    def __init__(self, videos: dict[str, list[VideoMetadata]]) -> None:
        self._videos = videos

    async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]:
        return self._videos.get(channel_id, [])


class _FakeTranscriptFetcher:
    def __init__(self, *, result: FetchedTranscript) -> None:
        self._result = result

    async def fetch(self, video_id: str, languages=None) -> FetchedTranscript:
        return self._result


class _CapturingArticleRepo:
    def __init__(self) -> None:
        self.received: list[ArticleIn] = []

    async def upsert_many(self, items: list[ArticleIn]) -> int:
        self.received.extend(items)
        return len(items)


@pytest.mark.asyncio
async def test_youtube_pipeline_keeps_recent_videos_only() -> None:
    now = datetime.now(UTC)
    videos = {
        "UC1": [
            VideoMetadata(
                video_id="v-old",
                title="old",
                url="https://www.youtube.com/watch?v=v-old",
                channel_id="UC1",
                published_at=now - timedelta(hours=48),
                description="",
                thumbnail_url=None,
            ),
            VideoMetadata(
                video_id="v-new",
                title="new",
                url="https://www.youtube.com/watch?v=v-new",
                channel_id="UC1",
                published_at=now - timedelta(hours=2),
                description="",
                thumbnail_url=None,
            ),
        ]
    }
    repo = _CapturingArticleRepo()
    pipeline = YouTubePipeline(
        fetcher=_FakeFeedFetcher(videos),
        transcripts=_FakeTranscriptFetcher(
            result=FetchedTranscript(text="t", segments=[], error=None)
        ),
        repo=repo,
        channels=[{"name": "chan", "channel_id": "UC1"}],
        transcript_concurrency=1,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert stats.status is ScraperRunStatus.SUCCESS
    assert stats.kept == 1
    assert stats.inserted == 1
    assert stats.transcripts_fetched == 1
    assert repo.received[0].external_id == "v-new"
    assert repo.received[0].content_text == "t"


@pytest.mark.asyncio
async def test_youtube_pipeline_records_transcript_failure_without_dropping_row() -> None:
    now = datetime.now(UTC)
    videos = {
        "UC1": [
            VideoMetadata(
                video_id="v1",
                title="v1",
                url="https://www.youtube.com/watch?v=v1",
                channel_id="UC1",
                published_at=now - timedelta(hours=1),
                description="",
                thumbnail_url=None,
            )
        ]
    }
    repo = _CapturingArticleRepo()
    pipeline = YouTubePipeline(
        fetcher=_FakeFeedFetcher(videos),
        transcripts=_FakeTranscriptFetcher(
            result=FetchedTranscript(text=None, segments=None, error="blocked")
        ),
        repo=repo,
        channels=[{"name": "c", "channel_id": "UC1"}],
        transcript_concurrency=1,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert stats.transcripts_failed == 1
    assert stats.kept == 1
    assert repo.received[0].content_text is None
    assert repo.received[0].raw["transcript_error"] == "blocked"


@pytest.mark.asyncio
async def test_youtube_pipeline_channel_error_isolated() -> None:
    class _ErrFetcher:
        async def list_recent_videos(self, channel_id: str):
            if channel_id == "UC_bad":
                raise RuntimeError("boom")
            return []

    repo = _CapturingArticleRepo()
    pipeline = YouTubePipeline(
        fetcher=_ErrFetcher(),
        transcripts=_FakeTranscriptFetcher(
            result=FetchedTranscript(text=None, segments=None, error=None)
        ),
        repo=repo,
        channels=[
            {"name": "a", "channel_id": "UC_ok"},
            {"name": "b", "channel_id": "UC_bad"},
        ],
        transcript_concurrency=1,
    )
    stats = await pipeline.run(lookback_hours=24)
    # One channel errored, one had no items — overall success since some work happened
    assert len(stats.errors) == 1
    assert stats.errors[0]["channel_id"] == "UC_bad"
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_pipelines_youtube.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.pipelines.youtube'`

- [ ] **Step 3: Implement `YouTubePipeline`**

Create `services/scraper/src/news_scraper/pipelines/youtube.py`:

```python
"""YouTube pipeline — feedparser + transcript API → ArticleIn upsert."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol

from news_observability.logging import get_logger
from news_schemas.article import ArticleIn, SourceType
from news_schemas.scraper_run import (
    PipelineName,
    ScraperRunStatus,
    YouTubeStats,
)

from news_scraper.pipelines.adapters import (
    FetchedTranscript,
    TranscriptFetcher,
    VideoMetadata,
    YouTubeFeedFetcher,
)

_log = get_logger("youtube_pipeline")


class _ArticleRepo(Protocol):
    async def upsert_many(self, items: list[ArticleIn]) -> int: ...


class YouTubePipeline:
    name = PipelineName.YOUTUBE

    def __init__(
        self,
        *,
        fetcher: YouTubeFeedFetcher,
        transcripts: TranscriptFetcher,
        repo: _ArticleRepo,
        channels: list[dict[str, str]],
        transcript_concurrency: int = 3,
    ) -> None:
        self._fetcher = fetcher
        self._transcripts = transcripts
        self._repo = repo
        self._channels = channels
        self._transcript_concurrency = transcript_concurrency

    async def run(self, *, lookback_hours: int) -> YouTubeStats:
        t0 = perf_counter()
        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        stats = YouTubeStats(status=ScraperRunStatus.SUCCESS)
        sem = asyncio.Semaphore(self._transcript_concurrency)
        seen: set[str] = set()
        articles: list[ArticleIn] = []

        async def process_video(v: VideoMetadata, channel_name: str) -> None:
            async with sem:
                transcript = await self._transcripts.fetch(v.video_id)
            article = self._to_article(v, channel_name, transcript)
            key = f"{article.source_name}::{article.external_id}"
            if key in seen:
                return
            seen.add(key)
            articles.append(article)
            if transcript.text is not None:
                stats.transcripts_fetched += 1
            else:
                stats.transcripts_failed += 1

        async def process_channel(ch: dict[str, str]) -> None:
            try:
                videos = await self._fetcher.list_recent_videos(ch["channel_id"])
            except Exception as exc:
                stats.errors.append(
                    {"channel_id": ch["channel_id"], "error": str(exc)}
                )
                return
            stats.fetched += len(videos)
            recent = [
                v for v in videos
                if v.published_at is not None and v.published_at >= cutoff
            ]
            stats.skipped_old += len(videos) - len(recent)
            await asyncio.gather(*(process_video(v, ch["name"]) for v in recent))

        await asyncio.gather(*(process_channel(c) for c in self._channels))
        stats.kept = len(articles)
        try:
            stats.inserted = await self._repo.upsert_many(articles)
        except Exception as exc:
            _log.exception("youtube upsert failed: {}", exc)
            stats.status = ScraperRunStatus.FAILED
            stats.errors.append({"stage": "upsert", "error": str(exc)})
        stats.duration_seconds = perf_counter() - t0
        return stats

    @staticmethod
    def _to_article(
        v: VideoMetadata, channel_name: str, transcript: FetchedTranscript
    ) -> ArticleIn:
        raw: dict[str, Any] = {
            "channel_id": v.channel_id,
            "thumbnail_url": v.thumbnail_url,
            "description": v.description,
            "transcript_segments": transcript.segments,
            "transcript_error": transcript.error,
            "has_transcript": transcript.text is not None,
        }
        return ArticleIn(
            source_type=SourceType.YOUTUBE,
            source_name=channel_name,
            external_id=v.video_id,
            title=v.title,
            url=v.url,  # type: ignore[arg-type]
            author=channel_name,
            published_at=v.published_at,
            content_text=transcript.text,
            tags=[],
            raw=raw,
        )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_pipelines_youtube.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/youtube.py \
        services/scraper/src/news_scraper/tests/unit/test_pipelines_youtube.py
git commit -m "feat(scraper): YouTubePipeline with transcript concurrency + error isolation"
```

---

### Task 6.2: `RSSPipeline`

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/rss.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_pipelines_rss.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_pipelines_rss.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from news_config.loader import RSSFeedConfig
from news_schemas.article import ArticleIn
from news_schemas.scraper_run import ScraperRunStatus
from news_scraper.pipelines.rss import RSSPipeline


class _FakeFetcher:
    def __init__(self, payloads: dict[str, dict]) -> None:
        self._payloads = payloads

    async def get_feed(self, url: str, count: int = 15) -> dict:
        if url not in self._payloads:
            raise RuntimeError(f"no fake payload for {url}")
        return self._payloads[url]


class _CapturingRepo:
    def __init__(self) -> None:
        self.received: list[ArticleIn] = []

    async def upsert_many(self, items: list[ArticleIn]) -> int:
        self.received.extend(items)
        return len(items)


@pytest.mark.asyncio
async def test_rss_pipeline_filters_by_cutoff_and_dedupes() -> None:
    now = datetime.now(UTC).isoformat()
    old = (datetime.now(UTC) - timedelta(hours=72)).isoformat()
    payloads = {
        "https://a/rss": {
            "title": "A",
            "items": [
                {"guid": "g1", "title": "t1", "link": "https://a/1", "pubDate": now},
                {"guid": "g1", "title": "t1", "link": "https://a/1", "pubDate": now},
                {"guid": "g2", "title": "t2", "link": "https://a/2", "pubDate": old},
            ],
        },
    }
    repo = _CapturingRepo()
    pipeline = RSSPipeline(
        fetcher=_FakeFetcher(payloads),
        repo=repo,
        feeds=[RSSFeedConfig(name="a", url="https://a/rss")],
        feed_concurrency=2,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert stats.status is ScraperRunStatus.SUCCESS
    assert stats.kept == 1
    assert stats.inserted == 1
    assert repo.received[0].external_id == "g1"


@pytest.mark.asyncio
async def test_rss_pipeline_records_per_feed_error() -> None:
    class _FailFetcher:
        async def get_feed(self, url: str, count: int = 15) -> dict:
            raise RuntimeError("down")

    repo = _CapturingRepo()
    pipeline = RSSPipeline(
        fetcher=_FailFetcher(),
        repo=repo,
        feeds=[
            RSSFeedConfig(name="a", url="https://a/rss"),
            RSSFeedConfig(name="b", url="https://b/rss"),
        ],
        feed_concurrency=2,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert len(stats.errors) == 2
    assert stats.status is ScraperRunStatus.FAILED
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_pipelines_rss.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.pipelines.rss'`

- [ ] **Step 3: Implement `RSSPipeline`**

Create `services/scraper/src/news_scraper/pipelines/rss.py`:

```python
"""RSS pipeline — fetch via rss-mcp, normalize, upsert."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol

from dateutil import parser as date_parser
from news_config.loader import RSSFeedConfig
from news_observability.logging import get_logger
from news_schemas.article import ArticleIn, SourceType
from news_schemas.scraper_run import PipelineName, PipelineStats, ScraperRunStatus

from news_scraper.pipelines.adapters import FeedFetcher

_log = get_logger("rss_pipeline")


class _ArticleRepo(Protocol):
    async def upsert_many(self, items: list[ArticleIn]) -> int: ...


def _parse_pub_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = date_parser.parse(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _stable_dedup_key(item: dict[str, Any]) -> str:
    if item.get("guid"):
        return str(item["guid"])
    if item.get("link"):
        return str(item["link"])
    fingerprint = f"{item.get('title', '')}|{item.get('pubDate', '')}"
    return "sha256:" + hashlib.sha256(fingerprint.encode()).hexdigest()


class RSSPipeline:
    name = PipelineName.RSS

    def __init__(
        self,
        *,
        fetcher: FeedFetcher,
        repo: _ArticleRepo,
        feeds: list[RSSFeedConfig],
        feed_concurrency: int = 5,
    ) -> None:
        self._fetcher = fetcher
        self._repo = repo
        self._feeds = feeds
        self._feed_concurrency = feed_concurrency

    async def run(self, *, lookback_hours: int) -> PipelineStats:
        t0 = perf_counter()
        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        stats = PipelineStats(status=ScraperRunStatus.SUCCESS)
        sem = asyncio.Semaphore(self._feed_concurrency)
        seen: set[str] = set()
        articles: list[ArticleIn] = []

        async def process_feed(feed: RSSFeedConfig) -> None:
            async with sem:
                try:
                    payload = await self._fetcher.get_feed(str(feed.url))
                except Exception as exc:
                    stats.errors.append({"feed": feed.name, "error": str(exc)})
                    return
            for item in payload.get("items", []):
                stats.fetched += 1
                pub = _parse_pub_date(item.get("pubDate"))
                if pub is None or pub < cutoff:
                    stats.skipped_old += 1
                    continue
                key = _stable_dedup_key(item)
                marker = f"{feed.name}::{key}"
                if marker in seen:
                    continue
                seen.add(marker)
                link = item.get("link")
                if not link:
                    stats.errors.append(
                        {"feed": feed.name, "guid": key, "error": "missing link"}
                    )
                    continue
                articles.append(
                    ArticleIn(
                        source_type=SourceType.RSS,
                        source_name=feed.name,
                        external_id=key,
                        title=item.get("title") or "(untitled)",
                        url=link,
                        author=item.get("author"),
                        published_at=pub,
                        content_text=item.get("description"),
                        tags=list(item.get("category") or []),
                        raw=item,
                    )
                )

        await asyncio.gather(*(process_feed(f) for f in self._feeds))
        stats.kept = len(articles)

        if stats.errors and stats.kept == 0:
            stats.status = ScraperRunStatus.FAILED
        else:
            try:
                stats.inserted = await self._repo.upsert_many(articles)
            except Exception as exc:
                _log.exception("rss upsert failed: {}", exc)
                stats.status = ScraperRunStatus.FAILED
                stats.errors.append({"stage": "upsert", "error": str(exc)})

        stats.duration_seconds = perf_counter() - t0
        return stats
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_pipelines_rss.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/rss.py \
        services/scraper/src/news_scraper/tests/unit/test_pipelines_rss.py
git commit -m "feat(scraper): RSSPipeline (rss-mcp-backed) with dedup + lookback"
```

---

### Task 6.3: `WebSearchPipeline`

**Files:**
- Create: `services/scraper/src/news_scraper/pipelines/web_search.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_pipelines_web_search.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_pipelines_web_search.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from news_config.loader import WebSearchSiteConfig
from news_schemas.article import ArticleIn
from news_schemas.audit import AuditLogIn
from news_schemas.scraper_run import ScraperRunStatus
from news_scraper.pipelines.adapters import (
    CrawlOutcome,
    SiteCrawlResult,
    WebSearchItem,
)
from news_scraper.pipelines.web_search import WebSearchPipeline


class _FakeCrawler:
    def __init__(self, outcomes: dict[str, CrawlOutcome]) -> None:
        self._outcomes = outcomes

    async def crawl_site(self, site, *, lookback_hours):
        if site.name not in self._outcomes:
            raise RuntimeError(f"no fake outcome for {site.name}")
        return self._outcomes[site.name]


class _CapturingRepo:
    def __init__(self) -> None:
        self.received: list[ArticleIn] = []

    async def upsert_many(self, items):
        self.received.extend(items)
        return len(items)


class _CapturingAudit:
    def __init__(self) -> None:
        self.records: list[AuditLogIn] = []

    async def log_decision(self, **kwargs):
        self.records.append(kwargs)


@pytest.mark.asyncio
async def test_web_search_pipeline_happy_path() -> None:
    outcome = CrawlOutcome(
        result=SiteCrawlResult(
            site_name="replit_blog",
            items=[
                WebSearchItem(
                    title="Post 1",
                    url="https://replit.com/blog/post-1",
                    published_at=datetime.now(UTC),
                )
            ],
        ),
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        requests=2,
        cost_usd=0.001,
        duration_ms=1000,
    )
    repo = _CapturingRepo()
    audit = _CapturingAudit()
    pipeline = WebSearchPipeline(
        crawler=_FakeCrawler({"replit_blog": outcome}),
        repo=repo,
        audit_logger=audit,
        sites=[
            WebSearchSiteConfig(
                name="replit_blog",
                url="https://replit.com/blog",
                list_selector_hint="hint",
            )
        ],
        site_concurrency=1,
        run_id=uuid4(),
    )
    stats = await pipeline.run(lookback_hours=48)
    assert stats.status is ScraperRunStatus.SUCCESS
    assert stats.sites_attempted == 1
    assert stats.sites_succeeded == 1
    assert stats.items_extracted == 1
    assert stats.total_cost_usd == pytest.approx(0.001)
    assert len(repo.received) == 1
    assert repo.received[0].source_name == "replit_blog"
    assert len(audit.records) == 1


@pytest.mark.asyncio
async def test_web_search_pipeline_isolates_site_failure() -> None:
    ok = CrawlOutcome(
        result=SiteCrawlResult(site_name="ok_site", items=[]),
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        requests=1,
        cost_usd=0.0,
        duration_ms=100,
    )
    repo = _CapturingRepo()
    audit = _CapturingAudit()
    pipeline = WebSearchPipeline(
        crawler=_FakeCrawler({"ok_site": ok}),
        repo=repo,
        audit_logger=audit,
        sites=[
            WebSearchSiteConfig(name="ok_site", url="https://ok.example/blog", list_selector_hint="h"),
            WebSearchSiteConfig(name="bad_site", url="https://bad.example/blog", list_selector_hint="h"),
        ],
        site_concurrency=1,
        run_id=uuid4(),
    )
    stats = await pipeline.run(lookback_hours=48)
    assert stats.sites_attempted == 2
    assert stats.sites_succeeded == 1
    assert stats.status is ScraperRunStatus.PARTIAL
    assert any(e.get("site") == "bad_site" for e in stats.errors)
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_pipelines_web_search.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.pipelines.web_search'`

- [ ] **Step 3: Implement `WebSearchPipeline`**

Create `services/scraper/src/news_scraper/pipelines/web_search.py`:

```python
"""Web-search pipeline — curated sites via Playwright agent."""

from __future__ import annotations

import asyncio
import hashlib
from time import perf_counter
from typing import Protocol
from uuid import UUID

from news_config.loader import WebSearchSiteConfig
from news_observability.logging import get_logger
from news_schemas.article import ArticleIn, SourceType
from news_schemas.audit import AgentName, DecisionType
from news_schemas.scraper_run import (
    PipelineName,
    ScraperRunStatus,
    WebSearchStats,
)

from news_scraper.pipelines.adapters import (
    CrawlOutcome,
    WebCrawler,
    WebSearchItem,
)

_log = get_logger("web_search_pipeline")


class _ArticleRepo(Protocol):
    async def upsert_many(self, items: list[ArticleIn]) -> int: ...


class _AuditLogger(Protocol):
    async def log_decision(
        self,
        *,
        agent_name: AgentName,
        user_id: UUID | None,
        decision_type: DecisionType,
        input_text: str,
        output_text: str,
        metadata: dict[str, object] | None = None,
    ) -> None: ...


class WebSearchPipeline:
    name = PipelineName.WEB_SEARCH

    def __init__(
        self,
        *,
        crawler: WebCrawler,
        repo: _ArticleRepo,
        audit_logger: _AuditLogger,
        sites: list[WebSearchSiteConfig],
        site_concurrency: int = 2,
        run_id: UUID,
    ) -> None:
        self._crawler = crawler
        self._repo = repo
        self._audit = audit_logger
        self._sites = sites
        self._site_concurrency = site_concurrency
        self._run_id = run_id

    async def run(self, *, lookback_hours: int) -> WebSearchStats:
        t0 = perf_counter()
        stats = WebSearchStats(status=ScraperRunStatus.SUCCESS)
        stats.sites_attempted = len(self._sites)
        sem = asyncio.Semaphore(self._site_concurrency)
        articles: list[ArticleIn] = []

        async def process(site: WebSearchSiteConfig) -> None:
            async with sem:
                try:
                    outcome: CrawlOutcome = await self._crawler.crawl_site(
                        site, lookback_hours=lookback_hours
                    )
                except Exception as exc:
                    stats.errors.append({"site": site.name, "error": str(exc)})
                    return
            stats.sites_succeeded += 1
            stats.items_extracted += len(outcome.result.items)
            stats.total_input_tokens += outcome.input_tokens
            stats.total_output_tokens += outcome.output_tokens
            if outcome.cost_usd is not None:
                stats.total_cost_usd += outcome.cost_usd
            for item in outcome.result.items:
                articles.append(self._to_article(item, site.name))
            await self._audit.log_decision(
                agent_name=AgentName.WEB_SEARCH,
                user_id=None,
                decision_type=DecisionType.SEARCH_RESULT,
                input_text=str(site.url),
                output_text=f"{len(outcome.result.items)} items extracted",
                metadata={
                    "site": site.name,
                    "input_tokens": outcome.input_tokens,
                    "output_tokens": outcome.output_tokens,
                    "total_tokens": outcome.total_tokens,
                    "requests": outcome.requests,
                    "estimated_cost_usd": outcome.cost_usd,
                    "duration_ms": outcome.duration_ms,
                    "run_id": str(self._run_id),
                },
            )

        await asyncio.gather(*(process(s) for s in self._sites))

        if stats.sites_succeeded == 0 and stats.sites_attempted > 0:
            stats.status = ScraperRunStatus.FAILED
        elif stats.sites_succeeded < stats.sites_attempted:
            stats.status = ScraperRunStatus.PARTIAL

        if articles and stats.status is not ScraperRunStatus.FAILED:
            try:
                stats.inserted = await self._repo.upsert_many(articles)
            except Exception as exc:
                _log.exception("web_search upsert failed: {}", exc)
                stats.status = ScraperRunStatus.FAILED
                stats.errors.append({"stage": "upsert", "error": str(exc)})

        stats.fetched = stats.items_extracted
        stats.kept = len(articles)
        stats.duration_seconds = perf_counter() - t0
        return stats

    @staticmethod
    def _to_article(item: WebSearchItem, site_name: str) -> ArticleIn:
        external_id = hashlib.sha256(str(item.url).encode()).hexdigest()
        return ArticleIn(
            source_type=SourceType.WEB_SEARCH,
            source_name=site_name,
            external_id=external_id,
            title=item.title,
            url=str(item.url),
            author=item.author,
            published_at=item.published_at,
            content_text=item.summary,
            tags=[],
            raw={"extracted_by": "web_search_agent"},
        )
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_pipelines_web_search.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/pipelines/web_search.py \
        services/scraper/src/news_scraper/tests/unit/test_pipelines_web_search.py
git commit -m "feat(scraper): WebSearchPipeline with audit logging + cost rollup"
```

---

## Phase 7 — Orchestrator, FastAPI, CLI

### Task 7.1: Orchestrator

**Files:**
- Create: `services/scraper/src/news_scraper/orchestrator.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Create `services/scraper/src/news_scraper/tests/unit/test_orchestrator.py`:

```python
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    RunStats,
    ScraperRunOut,
    ScraperRunStatus,
    YouTubeStats,
)
from news_scraper.orchestrator import run_all


class _FakePipeline:
    def __init__(self, name: PipelineName, stats: PipelineStats) -> None:
        self.name = name
        self._stats = stats

    async def run(self, *, lookback_hours: int) -> PipelineStats:
        return self._stats


class _RaisingPipeline:
    def __init__(self, name: PipelineName) -> None:
        self.name = name

    async def run(self, *, lookback_hours: int) -> PipelineStats:
        raise RuntimeError("pipeline crashed")


class _FakeRepo:
    def __init__(self) -> None:
        self.completed: tuple | None = None

    async def complete(
        self,
        run_id: UUID,
        status: ScraperRunStatus,
        stats: RunStats,
        error_message: str | None = None,
    ) -> ScraperRunOut:
        self.completed = (run_id, status, stats, error_message)
        return ScraperRunOut(
            id=run_id,
            trigger="api",
            status=status,
            started_at=__import__("datetime").datetime.now(
                __import__("datetime").UTC
            ),
            completed_at=None,
            lookback_hours=24,
            pipelines_requested=[],
            stats=stats,
            error_message=error_message,
        )


@pytest.mark.asyncio
async def test_run_all_marks_success_when_all_pipelines_succeed() -> None:
    run_id = uuid4()
    pipelines = [
        _FakePipeline(
            PipelineName.YOUTUBE,
            YouTubeStats(status=ScraperRunStatus.SUCCESS, inserted=1),
        ),
        _FakePipeline(
            PipelineName.RSS,
            PipelineStats(status=ScraperRunStatus.SUCCESS, inserted=2),
        ),
    ]
    repo = _FakeRepo()
    await run_all(run_id=run_id, lookback_hours=24, pipelines=pipelines, repo=repo)
    assert repo.completed is not None
    assert repo.completed[1] is ScraperRunStatus.SUCCESS


@pytest.mark.asyncio
async def test_run_all_marks_partial_on_mixed_outcome() -> None:
    run_id = uuid4()
    pipelines = [
        _FakePipeline(
            PipelineName.YOUTUBE,
            YouTubeStats(status=ScraperRunStatus.SUCCESS),
        ),
        _FakePipeline(
            PipelineName.RSS,
            PipelineStats(status=ScraperRunStatus.FAILED),
        ),
    ]
    repo = _FakeRepo()
    await run_all(run_id=run_id, lookback_hours=24, pipelines=pipelines, repo=repo)
    assert repo.completed[1] is ScraperRunStatus.PARTIAL


@pytest.mark.asyncio
async def test_run_all_isolates_pipeline_exceptions() -> None:
    run_id = uuid4()
    pipelines = [
        _FakePipeline(
            PipelineName.YOUTUBE,
            YouTubeStats(status=ScraperRunStatus.SUCCESS, inserted=3),
        ),
        _RaisingPipeline(PipelineName.RSS),
    ]
    repo = _FakeRepo()
    await run_all(run_id=run_id, lookback_hours=24, pipelines=pipelines, repo=repo)
    # YouTube success + RSS crash => partial
    assert repo.completed[1] is ScraperRunStatus.PARTIAL
    stats = repo.completed[2]
    assert stats.rss is not None
    assert stats.rss.status is ScraperRunStatus.FAILED
    assert any("pipeline crashed" in (e.get("error") or "") for e in stats.rss.errors)
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.orchestrator'`

- [ ] **Step 3: Implement the orchestrator**

Create `services/scraper/src/news_scraper/orchestrator.py`:

```python
"""Run orchestrator — fans out pipelines via asyncio.gather, records results."""

from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from news_observability.logging import get_logger
from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    RunStats,
    ScraperRunOut,
    ScraperRunStatus,
)

from news_scraper.pipelines.base import Pipeline
from news_scraper.stats import compute_run_status, merge_pipeline_results

_log = get_logger("orchestrator")


class _CompletableRepo(Protocol):
    async def complete(
        self,
        run_id: UUID,
        status: ScraperRunStatus,
        stats: RunStats,
        error_message: str | None = None,
    ) -> ScraperRunOut: ...


async def run_all(
    *,
    run_id: UUID,
    lookback_hours: int,
    pipelines: list[Pipeline],
    repo: _CompletableRepo,
) -> None:
    """Fan out pipelines, collect stats, complete the run row."""
    results = await asyncio.gather(
        *(p.run(lookback_hours=lookback_hours) for p in pipelines),
        return_exceptions=True,
    )

    stats_map: dict[PipelineName, PipelineStats] = {}
    for p, res in zip(pipelines, results, strict=True):
        if isinstance(res, Exception):
            _log.exception("pipeline {} crashed: {}", p.name, res)
            stats_map[p.name] = _synth_crash_stats(p.name, str(res))
        else:
            stats_map[p.name] = res

    status = compute_run_status(stats_map)
    merged = merge_pipeline_results(stats_map)
    try:
        await repo.complete(run_id, status, merged)
    except Exception as exc:
        _log.exception("scraper_runs.complete failed: {}", exc)


def _synth_crash_stats(name: PipelineName, err: str) -> PipelineStats:
    from news_schemas.scraper_run import WebSearchStats, YouTubeStats

    base_kwargs = {
        "status": ScraperRunStatus.FAILED,
        "errors": [{"stage": "pipeline", "error": err}],
    }
    if name is PipelineName.YOUTUBE:
        return YouTubeStats(**base_kwargs)
    if name is PipelineName.WEB_SEARCH:
        return WebSearchStats(**base_kwargs)
    return PipelineStats(**base_kwargs)
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_orchestrator.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add services/scraper/src/news_scraper/orchestrator.py \
        services/scraper/src/news_scraper/tests/unit/test_orchestrator.py
git commit -m "feat(scraper): orchestrator.run_all with per-pipeline isolation"
```

---

### Task 7.2: FastAPI app factory + routes

**Files:**
- Create: `services/scraper/src/news_scraper/api/__init__.py`
- Create: `services/scraper/src/news_scraper/api/dependencies.py`
- Create: `services/scraper/src/news_scraper/api/routes.py`
- Create: `services/scraper/src/news_scraper/main.py`

- [ ] **Step 1: Create empty api package**

Create `services/scraper/src/news_scraper/api/__init__.py`:

```python
```

- [ ] **Step 2: Create `dependencies.py`**

Create `services/scraper/src/news_scraper/api/dependencies.py`:

```python
"""FastAPI DI helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Protocol

from news_config.loader import SourcesConfig, load_sources
from news_config.settings import (
    AppSettings,
    LangfuseSettings,
    OpenAISettings,
    YouTubeProxySettings,
)
from news_db.engine import get_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from news_scraper.settings import ScraperSettings


class SessionFactory(Protocol):
    def __call__(self) -> AsyncIterator[AsyncSession]: ...


def get_session_factory() -> Callable[[], AsyncSession]:
    """Return a callable that yields a fresh AsyncSession.

    Used by background tasks which outlive the request lifecycle.
    """
    engine = get_engine()
    sm = async_sessionmaker(engine, expire_on_commit=False)
    return sm  # type: ignore[return-value]


def get_sources() -> SourcesConfig:
    return load_sources()


def get_scraper_settings() -> ScraperSettings:
    return ScraperSettings()


def get_openai_settings() -> OpenAISettings:
    return OpenAISettings()


def get_app_settings() -> AppSettings:
    return AppSettings()


def get_langfuse_settings() -> LangfuseSettings:
    return LangfuseSettings()


def get_youtube_proxy_settings() -> YouTubeProxySettings:
    return YouTubeProxySettings()
```

- [ ] **Step 3: Create `routes.py`**

Create `services/scraper/src/news_scraper/api/routes.py`:

```python
"""HTTP routes: /ingest, /ingest/{pipeline}, /runs, /runs/{id}, /healthz."""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_observability.audit import AuditLogger
from news_observability.logging import get_logger
from news_schemas.scraper_run import (
    PipelineName,
    ScraperRunIn,
    ScraperRunOut,
)
from pydantic import BaseModel, Field

from news_scraper.api.dependencies import (
    get_openai_settings,
    get_scraper_settings,
    get_session_factory,
    get_sources,
    get_youtube_proxy_settings,
)
from news_scraper.orchestrator import run_all
from news_scraper.pipelines.base import Pipeline
from news_scraper.pipelines.rss import RSSPipeline
from news_scraper.pipelines.rss_adapters import MCPFeedFetcher
from news_scraper.pipelines.web_search import WebSearchPipeline
from news_scraper.pipelines.web_search_adapters import PlaywrightAgentCrawler
from news_scraper.pipelines.youtube import YouTubePipeline
from news_scraper.pipelines.youtube_adapters import (
    FeedparserYouTubeFeedFetcher,
    YouTubeTranscriptApiFetcher,
)

_log = get_logger("api")
router = APIRouter()


class IngestRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=168)
    trigger: str = Field(default="api", pattern="^(api|cli|scheduler)$")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "git_sha": os.environ.get("GIT_SHA", "unknown")}


@router.post("/ingest", status_code=202)
async def ingest_all(
    req: IngestRequest,
    background: BackgroundTasks,
) -> ScraperRunOut:
    return await _launch(
        [PipelineName.YOUTUBE, PipelineName.RSS, PipelineName.WEB_SEARCH],
        req, background,
    )


@router.post("/ingest/youtube", status_code=202)
async def ingest_youtube(
    req: IngestRequest, background: BackgroundTasks
) -> ScraperRunOut:
    return await _launch([PipelineName.YOUTUBE], req, background)


@router.post("/ingest/rss", status_code=202)
async def ingest_rss(
    req: IngestRequest, background: BackgroundTasks
) -> ScraperRunOut:
    return await _launch([PipelineName.RSS], req, background)


@router.post("/ingest/web-search", status_code=202)
async def ingest_web_search(
    req: IngestRequest, background: BackgroundTasks
) -> ScraperRunOut:
    return await _launch([PipelineName.WEB_SEARCH], req, background)


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID) -> ScraperRunOut:
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        row = await repo.get_by_id(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return row


@router.get("/runs")
async def list_runs(limit: int = 20) -> list[ScraperRunOut]:
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        return await repo.get_recent(limit=limit)


async def _launch(
    pipelines: list[PipelineName],
    req: IngestRequest,
    background: BackgroundTasks,
) -> ScraperRunOut:
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        started = await repo.start(
            ScraperRunIn(
                trigger=req.trigger,
                lookback_hours=req.lookback_hours,
                pipelines_requested=pipelines,
            )
        )
    background.add_task(
        _run_background,
        run_id=started.id,
        lookback_hours=req.lookback_hours,
        pipeline_names=pipelines,
    )
    return started


async def _run_background(
    *,
    run_id: UUID,
    lookback_hours: int,
    pipeline_names: list[PipelineName],
) -> None:
    """Executed by FastAPI BackgroundTasks. Builds pipelines + calls run_all.

    The RSS pipeline owns an MCP subprocess whose lifetime must wrap the whole
    pipeline run, so we enter `create_rss_mcp_server` here (and only when RSS
    is requested) and perform `run_all` inside the async-with block.
    """
    from news_scraper.mcp_servers import create_rss_mcp_server

    session_factory = get_session_factory()
    sources = get_sources()
    scraper_settings = get_scraper_settings()
    openai_settings = get_openai_settings()
    yt_proxy = get_youtube_proxy_settings()

    async with session_factory() as session:
        article_repo = ArticleRepository(session)
        run_repo = ScraperRunRepository(session)
        audit_repo = AuditLogRepository(session)
        audit_logger = AuditLogger(audit_repo.insert)

        non_rss_pipelines: list[Pipeline] = []

        if PipelineName.YOUTUBE in pipeline_names and sources.youtube_enabled:
            non_rss_pipelines.append(
                YouTubePipeline(
                    fetcher=FeedparserYouTubeFeedFetcher(),
                    transcripts=YouTubeTranscriptApiFetcher(
                        proxy_enabled=yt_proxy.enabled,
                        proxy_username=yt_proxy.username,
                        proxy_password=yt_proxy.password,
                    ),
                    repo=article_repo,
                    channels=sources.youtube_channels,
                    transcript_concurrency=scraper_settings.youtube_transcript_concurrency,
                )
            )

        if (
            PipelineName.WEB_SEARCH in pipeline_names
            and sources.web_search is not None
            and sources.web_search.enabled
        ):
            non_rss_pipelines.append(
                WebSearchPipeline(
                    crawler=PlaywrightAgentCrawler(
                        model=openai_settings.model,
                        max_turns=scraper_settings.web_search_max_turns,
                        site_timeout=scraper_settings.web_search_site_timeout,
                    ),
                    repo=article_repo,
                    audit_logger=audit_logger,
                    sites=sources.web_search.sites,
                    site_concurrency=sources.web_search.max_concurrent_sites,
                    run_id=run_id,
                )
            )

        rss_requested = (
            PipelineName.RSS in pipeline_names
            and sources.rss is not None
            and sources.rss.enabled
        )

        if rss_requested:
            assert sources.rss is not None  # for type narrowing
            async with create_rss_mcp_server(
                scraper_settings.rss_mcp_path,
                timeout_seconds=sources.rss.mcp_timeout_seconds,
            ) as mcp_server:
                rss_pipeline = RSSPipeline(
                    fetcher=MCPFeedFetcher(mcp_server),
                    repo=article_repo,
                    feeds=sources.rss.feeds,
                    feed_concurrency=sources.rss.max_concurrent_feeds,
                )
                await run_all(
                    run_id=run_id,
                    lookback_hours=lookback_hours,
                    pipelines=[*non_rss_pipelines, rss_pipeline],
                    repo=run_repo,
                )
        else:
            await run_all(
                run_id=run_id,
                lookback_hours=lookback_hours,
                pipelines=non_rss_pipelines,
                repo=run_repo,
            )
```

- [ ] **Step 4: Create `main.py` (FastAPI app factory + lifespan)**

Create `services/scraper/src/news_scraper/main.py`:

```python
"""FastAPI app factory with startup logging, tracing, orphan sweep."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from news_db.engine import get_session
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_observability.logging import get_logger, setup_logging
from news_observability.tracing import configure_tracing

from news_scraper.api.routes import router

_log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    configure_tracing(enable_langfuse=True)
    try:
        async with get_session() as session:
            repo = ScraperRunRepository(session)
            count = await repo.mark_orphaned(
                older_than=datetime.now(UTC) - timedelta(hours=2)
            )
            if count:
                _log.info("orphan sweep flipped {} stale scraper_runs rows", count)
    except Exception as exc:  # DB may be unreachable at first boot
        _log.warning("orphan sweep skipped: {}", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="news-scraper", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
```

- [ ] **Step 5: Smoke — import the app**

Run: `uv run python -c "from news_scraper.main import app; print([r.path for r in app.routes])"`
Expected: output lists `/healthz`, `/ingest`, `/ingest/youtube`, `/ingest/rss`, `/ingest/web-search`, `/runs/{run_id}`, `/runs`.

- [ ] **Step 6: Commit**

```bash
git add services/scraper/src/news_scraper/api \
        services/scraper/src/news_scraper/main.py
git commit -m "feat(scraper): FastAPI app + routes + lifespan (logging/tracing/orphan sweep)"
```

---

### Task 7.3: CLI via Typer

**Files:**
- Create: `services/scraper/src/news_scraper/cli.py`
- Create: `services/scraper/src/news_scraper/__main__.py`
- Create: `services/scraper/src/news_scraper/tests/unit/test_cli.py`

- [ ] **Step 1: Write failing test (smoke)**

Create `services/scraper/src/news_scraper/tests/unit/test_cli.py`:

```python
from __future__ import annotations

from typer.testing import CliRunner

from news_scraper.cli import app as cli_app


def test_cli_help_lists_expected_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "ingest-youtube", "ingest-rss", "ingest-web", "runs", "run-show", "serve"):
        assert cmd in result.stdout
```

- [ ] **Step 2: Run — expect fail**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'news_scraper.cli'`

- [ ] **Step 3: Implement CLI**

Create `services/scraper/src/news_scraper/cli.py`:

```python
"""Typer CLI. Same pipeline code as the HTTP API; blocks until completion."""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import typer
from news_db.engine import get_session
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_observability.logging import setup_logging
from news_schemas.scraper_run import PipelineName, ScraperRunIn, ScraperRunStatus

from news_scraper.api.routes import _run_background  # reuse server plumbing

app = typer.Typer(no_args_is_help=True, help="News scraper CLI")


def _exit_code_for(status: ScraperRunStatus) -> int:
    match status:
        case ScraperRunStatus.SUCCESS:
            return 0
        case ScraperRunStatus.PARTIAL:
            return 1
        case ScraperRunStatus.FAILED:
            return 2
        case _:
            return 3


async def _start_and_run(
    pipelines: list[PipelineName], lookback_hours: int
) -> ScraperRunStatus:
    setup_logging()
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        started = await repo.start(
            ScraperRunIn(
                trigger="cli",
                lookback_hours=lookback_hours,
                pipelines_requested=pipelines,
            )
        )
    await _run_background(
        run_id=started.id,
        lookback_hours=lookback_hours,
        pipeline_names=pipelines,
    )
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        final = await repo.get_by_id(started.id)
        typer.echo(f"run {started.id} -> {final.status.value if final else 'unknown'}")
        return final.status if final else ScraperRunStatus.FAILED


@app.command()
def ingest(lookback_hours: int = 24) -> None:
    """Run all three pipelines."""
    status = asyncio.run(
        _start_and_run(
            [PipelineName.YOUTUBE, PipelineName.RSS, PipelineName.WEB_SEARCH],
            lookback_hours,
        )
    )
    sys.exit(_exit_code_for(status))


@app.command("ingest-youtube")
def ingest_youtube(lookback_hours: int = 24) -> None:
    sys.exit(
        _exit_code_for(asyncio.run(_start_and_run([PipelineName.YOUTUBE], lookback_hours)))
    )


@app.command("ingest-rss")
def ingest_rss(lookback_hours: int = 24) -> None:
    sys.exit(
        _exit_code_for(asyncio.run(_start_and_run([PipelineName.RSS], lookback_hours)))
    )


@app.command("ingest-web")
def ingest_web(lookback_hours: int = 48) -> None:
    sys.exit(
        _exit_code_for(asyncio.run(_start_and_run([PipelineName.WEB_SEARCH], lookback_hours)))
    )


@app.command()
def runs(limit: int = 20) -> None:
    """Show recent scraper runs."""
    async def _main() -> None:
        async with get_session() as session:
            repo = ScraperRunRepository(session)
            for r in await repo.get_recent(limit=limit):
                typer.echo(
                    f"{r.id}  {r.started_at.isoformat()}  {r.status.value:8}  "
                    f"{' '.join(p.value for p in r.pipelines_requested)}"
                )
    asyncio.run(_main())


@app.command("run-show")
def run_show(run_id: UUID) -> None:
    """Show a single run as JSON."""
    async def _main() -> None:
        async with get_session() as session:
            repo = ScraperRunRepository(session)
            r = await repo.get_by_id(run_id)
            if r is None:
                typer.echo(f"run {run_id} not found", err=True)
                sys.exit(2)
            typer.echo(r.model_dump_json(indent=2))
    asyncio.run(_main())


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server (uvicorn)."""
    import uvicorn
    uvicorn.run("news_scraper.main:app", host=host, port=port)
```

- [ ] **Step 4: Create `__main__.py`**

Create `services/scraper/src/news_scraper/__main__.py`:

```python
from news_scraper.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest services/scraper/src/news_scraper/tests/unit/test_cli.py -v`
Expected: PASS

Also verify: `uv run python -m news_scraper --help`
Expected: help text lists `ingest`, `ingest-youtube`, `ingest-rss`, `ingest-web`, `runs`, `run-show`, `serve`.

- [ ] **Step 6: Commit**

```bash
git add services/scraper/src/news_scraper/cli.py \
        services/scraper/src/news_scraper/__main__.py \
        services/scraper/src/news_scraper/tests/unit/test_cli.py
git commit -m "feat(scraper): Typer CLI + python -m news_scraper dispatch"
```

---

### Task 7.4: FastAPI integration test (real DB, mocked adapters)

**Files:**
- Create: `tests/integration/test_scraper_api.py`

- [ ] **Step 1: Write failing test**

Create `tests/integration/test_scraper_api.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from news_db.engine import get_session
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_schemas.article import ArticleIn, SourceType
from news_schemas.scraper_run import (
    PipelineName,
    PipelineStats,
    ScraperRunStatus,
    YouTubeStats,
)
from news_scraper.main import create_app


@pytest.mark.asyncio
async def test_healthz_returns_ok(session) -> None:  # noqa: ARG001
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_post_ingest_creates_run_row(session) -> None:  # noqa: ARG001
    # Stub the whole background run so we only test the 202 surface here.
    async def _noop(**kwargs):
        return None

    with patch(
        "news_scraper.api.routes._run_background", side_effect=_noop
    ):
        client = TestClient(create_app())
        resp = client.post("/ingest", json={"lookback_hours": 12, "trigger": "api"})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "running"
    assert body["lookback_hours"] == 12
    assert set(body["pipelines_requested"]) == {"youtube", "rss", "web_search"}

    async with get_session() as s:
        repo = ScraperRunRepository(s)
        row = await repo.get_by_id(body["id"])
        assert row is not None
        assert row.status is ScraperRunStatus.RUNNING


@pytest.mark.asyncio
async def test_runs_endpoint_lists_recent(session) -> None:  # noqa: ARG001
    async def _noop(**kwargs):
        return None

    with patch(
        "news_scraper.api.routes._run_background", side_effect=_noop
    ):
        client = TestClient(create_app())
        for _ in range(2):
            resp = client.post("/ingest/rss", json={})
            assert resp.status_code == 202

    client = TestClient(create_app())
    resp = client.get("/runs?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
```

- [ ] **Step 2: Run — expect pass**

Run: `uv run pytest tests/integration/test_scraper_api.py -v`
Expected: PASS (3 tests)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_scraper_api.py
git commit -m "test(integration): FastAPI TestClient + real DB smoke for scraper API"
```

---

## Phase 8 — Dockerfile, deploy.py, live tests, docs, cleanup

### Task 8.1: Dockerfile + .dockerignore

**Files:**
- Create: `services/scraper/Dockerfile`
- Create: `services/scraper/.dockerignore`

- [ ] **Step 1: Write the Dockerfile**

Create `services/scraper/Dockerfile`:

```dockerfile
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libxshmfence1 \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/scraper/pyproject.toml ./services/scraper/pyproject.toml
COPY services/scraper/src ./services/scraper/src

RUN uv sync --frozen --no-dev \
  --package news_scraper \
  --package news_db --package news_schemas --package news_config --package news_observability

COPY rss-mcp/dist ./rss-mcp/dist
COPY rss-mcp/package.json ./rss-mcp/package.json
RUN cd rss-mcp && npm install --production

RUN npx -y @playwright/mcp@latest --help >/dev/null 2>&1 || true
RUN npx -y playwright install chromium --with-deps

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    RSS_MCP_PATH=/app/rss-mcp/dist/index.js \
    NODE_ENV=production

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "news_scraper.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `.dockerignore`**

Create `services/scraper/.dockerignore`:

```
.venv
**/__pycache__
**/*.pyc
.mypy_cache
.ruff_cache
.pytest_cache
.coverage
htmlcov
services/scraper/_legacy
services/scraper/tests
tests
docs
rss-mcp/node_modules
rss-mcp/src
**/.env
**/.git
```

- [ ] **Step 3: Smoke build (skip if Docker unavailable)**

Run: `docker build -f services/scraper/Dockerfile -t news-scraper:local --build-arg GIT_SHA=$(git rev-parse HEAD) .`
Expected: image builds successfully (may take 5–10 minutes on first build because of Chromium).

If the build fails due to an environmental issue, note the error but proceed. The Dockerfile is still committed.

- [ ] **Step 4: Commit**

```bash
git add services/scraper/Dockerfile services/scraper/.dockerignore
git commit -m "feat(scraper): Dockerfile + .dockerignore (Python 3.12 + Node 20 + Playwright)"
```

---

### Task 8.2: `deploy.py` — build mode only (deploy mode stubs out until #6)

**Files:**
- Create: `services/scraper/deploy.py`

- [ ] **Step 1: Write `deploy.py`**

Create `services/scraper/deploy.py`:

```python
"""Scraper deploy orchestrator.

Two modes:
  build   — docker build + push to ECR (works standalone; needs ECR repo to exist)
  deploy  — calls into #6's Terraform to update the ECS service (blocked until
            that module lands; raises a clear error until then)

Examples:
  uv run python services/scraper/deploy.py --mode build
  uv run python services/scraper/deploy.py --mode deploy --env dev
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import boto3


def _profile() -> str:
    return os.environ.get("AWS_PROFILE", "aiengineer")


def _session() -> boto3.Session:
    return boto3.Session(profile_name=_profile())


def _account_id(session: boto3.Session) -> str:
    return session.client("sts").get_caller_identity()["Account"]


def _region(session: boto3.Session) -> str:
    region = session.region_name or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        raise RuntimeError("AWS region not set (profile default, AWS_REGION, or AWS_DEFAULT_REGION)")
    return region


def _ecr_repo() -> str:
    return os.environ.get("ECR_REPO_NAME", "news-scraper")


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _full_image_uri(session: boto3.Session, tag: str) -> str:
    return f"{_account_id(session)}.dkr.ecr.{_region(session)}.amazonaws.com/{_ecr_repo()}:{tag}"


def _ecr_login(session: boto3.Session) -> None:
    region = _region(session)
    account = _account_id(session)
    cmd = (
        f"aws ecr get-login-password --region {region} --profile {_profile()} | "
        f"docker login --username AWS --password-stdin {account}.dkr.ecr.{region}.amazonaws.com"
    )
    subprocess.run(cmd, shell=True, check=True)


def _build_image(sha_tag: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [
            "docker", "build",
            "-f", str(Path(__file__).parent / "Dockerfile"),
            "-t", sha_tag,
            "--build-arg", f"GIT_SHA={_git_sha()}",
            str(repo_root),
        ],
        check=True,
    )


def _push_image(session: boto3.Session, sha_tag: str) -> None:
    uri_sha = _full_image_uri(session, _git_sha())
    uri_latest = _full_image_uri(session, "latest")
    subprocess.run(["docker", "tag", sha_tag, uri_sha], check=True)
    subprocess.run(["docker", "tag", sha_tag, uri_latest], check=True)
    subprocess.run(["docker", "push", uri_sha], check=True)
    subprocess.run(["docker", "push", uri_latest], check=True)
    print(f"pushed {uri_sha}")
    print(f"pushed {uri_latest}")


def cmd_build() -> int:
    session = _session()
    _ecr_login(session)
    local_tag = f"news-scraper:{_git_sha()}"
    _build_image(local_tag)
    _push_image(session, local_tag)
    return 0


def cmd_deploy(env: str) -> int:
    # Invoke #6's Terraform. Until #6 lands, this errors with a clear message.
    tf_dir = Path(__file__).resolve().parents[2] / "infra" / "envs" / env
    if not tf_dir.exists():
        print(
            f"ERROR: {tf_dir} does not exist yet. #6 Terraform must be in "
            "place before `deploy` can run. Use --mode build until then.",
            file=sys.stderr,
        )
        return 3
    sha = _git_sha()
    subprocess.run(
        [
            "terraform", "apply",
            "-replace=module.scraper.aws_ecs_service.this",
            f"-var=image_tag={sha}",
            "-auto-approve",
        ],
        cwd=tf_dir,
        check=True,
        env={**os.environ, "AWS_PROFILE": _profile()},
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["build", "deploy"], required=True)
    parser.add_argument("--env", default="dev")
    args = parser.parse_args()
    if args.mode == "build":
        return cmd_build()
    return cmd_deploy(args.env)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke — `--help`**

Run: `uv run python services/scraper/deploy.py --help`
Expected: argparse help output with `--mode`, `--env`.

- [ ] **Step 3: Commit**

```bash
git add services/scraper/deploy.py
git commit -m "feat(scraper): deploy.py with build (ECR push) + deploy (Terraform) modes"
```

---

### Task 8.3: Live tests (`@pytest.mark.live`)

**Files:**
- Create: `services/scraper/src/news_scraper/tests/live/__init__.py`
- Create: `services/scraper/src/news_scraper/tests/live/test_rss_mcp_live.py`
- Create: `services/scraper/src/news_scraper/tests/live/test_youtube_live.py`
- Modify: `pyproject.toml` (register `live` marker)

- [ ] **Step 1: Register the `live` marker**

Edit `pyproject.toml` (root); replace the `[tool.pytest.ini_options]` block with:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["packages", "services", "tests"]
pythonpath = ["."]
markers = [
    "live: tests that hit real external services (rss-mcp, YouTube, Playwright). Run with `pytest -m live`.",
]
addopts = "-m 'not live'"
```

- [ ] **Step 2: Create live tests package**

Create `services/scraper/src/news_scraper/tests/live/__init__.py` (empty):

```python
```

- [ ] **Step 3: Live RSS test**

Create `services/scraper/src/news_scraper/tests/live/test_rss_mcp_live.py`:

```python
"""Spawns rss-mcp against openai_news RSS. Run: uv run pytest -m live."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from news_scraper.mcp_servers import create_rss_mcp_server
from news_scraper.pipelines.rss_adapters import MCPFeedFetcher


@pytest.mark.live
@pytest.mark.asyncio
async def test_openai_news_feed_returns_items() -> None:
    path = os.environ.get(
        "RSS_MCP_PATH",
        str(Path(__file__).resolve().parents[5] / "rss-mcp" / "dist" / "index.js"),
    )
    assert Path(path).exists(), f"rss-mcp dist missing at {path}"
    async with create_rss_mcp_server(path, timeout_seconds=60) as server:
        fetcher = MCPFeedFetcher(server)
        result = await fetcher.get_feed(
            "https://openai.com/news/rss.xml", count=3
        )
    assert "items" in result
    assert isinstance(result["items"], list)
    # Don't assert length — feed may legitimately be empty. Just assert shape.
```

- [ ] **Step 4: Live YouTube test**

Create `services/scraper/src/news_scraper/tests/live/test_youtube_live.py`:

```python
"""Hits YouTube RSS for one channel. Run: uv run pytest -m live."""

from __future__ import annotations

import pytest
from news_scraper.pipelines.youtube_adapters import FeedparserYouTubeFeedFetcher


@pytest.mark.live
@pytest.mark.asyncio
async def test_real_channel_returns_video_metadata() -> None:
    fetcher = FeedparserYouTubeFeedFetcher()
    videos = await fetcher.list_recent_videos("UC_x5XG1OV2P6uZZ5FSM9Ttw")  # Google Developers
    assert isinstance(videos, list)
    if videos:
        assert videos[0].video_id
        assert videos[0].url.startswith("https://")
```

- [ ] **Step 5: Verify CI-default skip + explicit live-opt-in**

Run: `uv run pytest services/scraper/src/news_scraper/tests/live -v`
Expected: 2 tests **deselected** because `-m 'not live'` is the default in `addopts`.

Run: `uv run pytest services/scraper/src/news_scraper/tests/live -m live -v`
Expected: tests execute (may be slow; network-dependent). It is OK if they pass when the network is up and the rss-mcp `dist/` is present.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml \
        services/scraper/src/news_scraper/tests/live
git commit -m "test(scraper): live-mark smoke tests for rss-mcp + YouTube RSS"
```

---

### Task 8.4: `docs/ecs-express-bootstrap.md`

**Files:**
- Create: `docs/ecs-express-bootstrap.md`

- [ ] **Step 1: Write the doc**

Create `docs/ecs-express-bootstrap.md`:

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add docs/ecs-express-bootstrap.md
git commit -m "docs: ECS Express one-time bootstrap notes (retires when #6 lands)"
```

---

### Task 8.5: `.env.example` additions

**Files:**
- Modify: `.env.example` (root)

- [ ] **Step 1: Append new vars**

Append to `.env.example`:

```
# ---------- Sub-project #1 (Ingestion) ----------
# Deploy.py (not used at runtime)
AWS_PROFILE=aiengineer
ECR_REPO_NAME=news-scraper
ECS_CLUSTER=news-aggregator
ECS_SERVICE_NAME=news-scraper

# Runtime
OPENAI_MODEL=gpt-5.5-mini
RSS_MCP_PATH=./rss-mcp/dist/index.js
WEB_SEARCH_MAX_TURNS=15
WEB_SEARCH_SITE_TIMEOUT=120
YOUTUBE_TRANSCRIPT_CONCURRENCY=3
RSS_FEED_CONCURRENCY=5
WEB_SEARCH_SITE_CONCURRENCY=2
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs(env): add scraper variables to .env.example"
```

---

### Task 8.6: Makefile targets for scraper

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Add new targets**

Edit `Makefile`; append these targets (in the `quality` / `tests` section, before `# ---------- database ----------`):

```makefile
# ---------- scraper ----------

test-scraper-unit: ## Scraper unit tests (no Docker required)
	$(PYTEST) services/scraper/src/news_scraper/tests/unit -v

test-scraper-live: ## Scraper live smoke tests (hits real rss-mcp + YouTube)
	$(PYTEST) services/scraper/src/news_scraper/tests -m live -v

scraper-build: ## Build scraper Docker image locally
	docker build -f services/scraper/Dockerfile -t news-scraper:$(shell git rev-parse HEAD) \
	  --build-arg GIT_SHA=$(shell git rev-parse HEAD) .

scraper-deploy-build: ## Build + push scraper image to ECR
	uv run python services/scraper/deploy.py --mode build

scraper-deploy: ## Full scraper deploy via Terraform (requires #6 infra)
	uv run python services/scraper/deploy.py --mode deploy --env dev

scraper-serve: ## Run scraper FastAPI locally
	uv run python -m news_scraper serve

scraper-ingest: ## Run all pipelines locally and block until done
	uv run python -m news_scraper ingest --lookback-hours 24
```

Add the new targets to `.PHONY`:

```makefile
.PHONY: help install install-dev pre-commit-install \
        fmt lint typecheck check \
        test test-unit test-integration \
        test-scraper-unit test-scraper-live \
        scraper-build scraper-deploy-build scraper-deploy \
        scraper-serve scraper-ingest \
        migrate migrate-down migrate-rev migration-history migration-current \
        seed reset-db \
        clean tag-foundation tag-ingestion
```

Add the new tag target at the bottom:

```makefile
tag-ingestion: ## Tag sub-project #1 ingestion
	git tag -f -a ingestion-v0.2.0 -m "Sub-project #1 Ingestion"
	@echo "Push with: git push origin ingestion-v0.2.0 --force"
```

- [ ] **Step 2: Verify**

Run: `make help | grep scraper`
Expected: shows all new scraper targets.

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "build(make): add scraper targets (test/build/deploy/serve/ingest)"
```

---

### Task 8.7: Delete `_legacy/`

**Files:**
- Delete: `services/scraper/_legacy/`
- Modify: `ruff.toml` (remove the `_legacy` exclude — no longer needed)
- Modify: `mypy.ini` (remove the `_legacy` exclude)

- [ ] **Step 1: Remove legacy code**

Run:

```bash
git rm -r services/scraper/_legacy
```

- [ ] **Step 2: Trim `ruff.toml`**

Edit `ruff.toml` and remove the `"services/scraper/_legacy"` line from the `exclude` list.

- [ ] **Step 3: Trim `mypy.ini`**

Edit `mypy.ini` and remove `^services/scraper/_legacy/` from the `exclude` regex. The remaining regex:

```
exclude = (?x)(
    /tests/
    | ^tests/
    | /alembic/versions/
  )
```

- [ ] **Step 4: Verify nothing references _legacy**

Run: `rg -n 'scraper/_legacy' || true`
Expected: no matches (or only in commit messages).

Run: `make check`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add services/scraper ruff.toml mypy.ini
git commit -m "chore(scraper): remove _legacy/ prototypes (superseded by new pipelines)"
```

---

### Task 8.8: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace "Current status"**

Edit `README.md`; replace the `## Current status` block's body with:

```markdown
**Sub-project #0 (Foundation)** and **Sub-project #1 (Ingestion)** are
implemented.

- Foundation ships the `packages/` workspace + schema. Tag `foundation-v0.1.1`.
- Ingestion ships `services/scraper/` — a FastAPI + CLI service with three
  pipelines (YouTube RSS, blog RSS via rss-mcp, web search via Playwright MCP
  + OpenAI Agents SDK). Tag `ingestion-v0.2.0`.

See [docs/superpowers/specs/](docs/superpowers/specs/) for design specs and
[docs/superpowers/plans/](docs/superpowers/plans/) for implementation plans.
Full sub-project breakdown (#0 through #6) is in [AGENTS.md](AGENTS.md).
```

- [ ] **Step 2: Add a "Running the scraper" section before "Day-to-day commands"**

Insert:

```markdown
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
make scraper-build               # local docker build
make scraper-deploy-build        # build + push to ECR (requires AWS_PROFILE=aiengineer)
make scraper-deploy              # full deploy via Terraform (requires #6 infra)
```

See [docs/ecs-express-bootstrap.md](docs/ecs-express-bootstrap.md) for one-time
AWS setup until sub-project #6 codifies it in Terraform.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document sub-project #1 and scraper commands"
```

---

### Task 8.9: Final green check + tag

**Files:** (no code changes)

- [ ] **Step 1: Run full `make check`**

Run: `make check`
Expected: all green — ruff, mypy, unit, integration.

If any test fails, pause and fix (this is the last gate before tagging).

- [ ] **Step 2: Run live suite locally**

Run: `make test-scraper-live`
Expected: both tests pass (network-dependent; rerun if flaky).

- [ ] **Step 3: Tag**

```bash
git tag -a ingestion-v0.2.0 -m "Sub-project #1 Ingestion Pipeline"
```

- [ ] **Step 4: Push branch + tag (on user approval)**

Do NOT push automatically. Pause and confirm with the user. When approved:

```bash
git push -u origin sub-project#1
git push origin ingestion-v0.2.0
```

---

## Appendix A — Test command cheat sheet

```sh
# Every scraper unit test
uv run pytest services/scraper/src/news_scraper/tests/unit -v

# Every integration test covering scraper
uv run pytest tests/integration -k scraper -v

# Full matrix (what CI runs)
make check

# Live smokes (rss-mcp + YouTube RSS) — local only
make test-scraper-live
```

## Appendix B — Pipeline invariants (re-verify during implementation)

- `ArticleIn.external_id` must be stable across runs for each source, so dedup works:
  - YouTube: the video_id (not URL)
  - RSS: `guid → link → sha256(title+pubDate)` (via `_stable_dedup_key`)
  - web_search: `sha256(url)`
- `ArticleIn.url` is a `HttpUrl`; coerce legacy raw strings with `str(...)` when loading.
- `YouTubeTranscriptApi` calls are sync and must be wrapped in `asyncio.to_thread(...)`.
- rss-mcp returns a JSON string inside `ToolCallResult.content[0].text`; parse with `json.loads`.
- Playwright agent tool calls are internal to the Agents SDK — we never call them directly.
- `AuditLogger.log_decision` kwargs use `input_text`/`output_text` (not `input_summary`), and passes `metadata` through as-is. Size-capping happens inside the logger.

## Appendix C — Why some design choices exist

- **Adapter Protocols**: every MCP / network call is mockable, so CI never spawns Node.
- **Fire-and-forget audit**: audit failures never break ingestion (pattern from Foundation).
- **scraper_runs UUID PK**: run_id is issued to the client the moment `POST /ingest` returns; no sequence-generator race.
- **RSS pipeline owns its MCP subprocess for the whole run**: keeps subprocess count at 1 even when 18 feeds are fanned out.
- **Per-site Playwright subprocess in web-search**: cleanest isolation; browser crashes don't cascade.
- **LLM cost tracking in `news_observability.costs`**: reused verbatim by #2 (Digest/Editor/Email) with no changes.

## Self-review checklist (author)

- Spec §1 scope — covered by Tasks 1.1–1.5 (DB) + 4.1 (scaffold) + 8.1 (Dockerfile) + 8.2 (deploy.py).
- Spec §2 architectural decisions — every row either implemented or non-goal.
- Spec §3 repo layout — every file listed is created by a task.
- Spec §4 data model — migration 0002 covers all columns + indexes + CHECK.
- Spec §5 API contract — `/ingest` + per-pipeline + `/runs` covered by Task 7.2; CLI by Task 7.3.
- Spec §6 per-pipeline design — Tasks 6.1/6.2/6.3 each match the normalization + adapter pattern from the spec.
- Spec §7 observability — logging/tracing in lifespan (Task 7.2 main.py); audit + usage in Task 6.3; cost module in Task 2.1.
- Spec §8 Dockerfile — Task 8.1 matches the spec verbatim.
- Spec §9 deploy.py — Task 8.2 implements `build` fully and stubs `deploy` with a clear error until #6.
- Spec §10 env vars — Task 8.5 adds them to `.env.example`.
- Spec §11 testing tiers — unit (throughout Phases 1–7), integration (Tasks 1.3/1.4/7.4), live (Task 8.3).
- Spec §12 non-goals — nothing in this plan creates a digest/editor/email agent, EventBridge cron, or Terraform module.
- Spec §13 risks — orphan sweep implemented in Task 7.2 lifespan; unknown-model cost in Task 2.1 tests; dual `:sha`+`:latest` tagging in Task 8.2.
- Placeholder scan — no "TBD", no "add validation", no "similar to task N", every step contains actual code or exact commands.
- Type consistency — `PipelineName` / `ScraperRunStatus` / `RunStats` spelled identically in every task; `ScraperRunRepository.complete` signature matches across Tasks 1.4 / 7.1 / 7.2.
