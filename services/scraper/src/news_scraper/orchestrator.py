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
        if isinstance(res, BaseException):
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

    base_kwargs: dict[str, object] = {
        "status": ScraperRunStatus.FAILED,
        "errors": [{"stage": "pipeline", "error": err}],
    }
    if name is PipelineName.YOUTUBE:
        return YouTubeStats(**base_kwargs)  # type: ignore[arg-type]
    if name is PipelineName.WEB_SEARCH:
        return WebSearchStats(**base_kwargs)  # type: ignore[arg-type]
    return PipelineStats(**base_kwargs)  # type: ignore[arg-type]
