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
