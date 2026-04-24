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
