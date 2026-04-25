from __future__ import annotations

from datetime import UTC, datetime
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
        self.completed: tuple[UUID, ScraperRunStatus, RunStats, str | None] | None = None

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
            started_at=datetime.now(UTC),
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
    assert repo.completed is not None
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
    assert repo.completed is not None
    assert repo.completed[1] is ScraperRunStatus.PARTIAL
    stats = repo.completed[2]
    assert stats.rss is not None
    assert stats.rss.status is ScraperRunStatus.FAILED
    assert any("pipeline crashed" in (e.get("error") or "") for e in stats.rss.errors)
