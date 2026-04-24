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
