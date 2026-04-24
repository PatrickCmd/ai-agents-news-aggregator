from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_schemas.scraper_run import (
    PipelineName,
    RunStats,
    ScraperRunIn,
    ScraperRunStatus,
    YouTubeStats,
)
from sqlalchemy import text
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
        youtube=YouTubeStats(status=ScraperRunStatus.SUCCESS, inserted=10, transcripts_fetched=5)
    )
    completed = await repo.complete(started.id, ScraperRunStatus.SUCCESS, stats)
    assert completed.status is ScraperRunStatus.SUCCESS
    assert completed.completed_at is not None
    assert completed.stats.youtube is not None
    assert completed.stats.youtube.inserted == 10


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_missing(session: AsyncSession) -> None:
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
    assert recent[0].started_at >= recent[-1].started_at


@pytest.mark.asyncio
async def test_mark_orphaned_flips_stale_running_rows(session: AsyncSession) -> None:
    repo = ScraperRunRepository(session)
    fresh = await repo.start(
        ScraperRunIn(
            trigger="api",
            lookback_hours=24,
            pipelines_requested=[PipelineName.RSS],
        )
    )
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
