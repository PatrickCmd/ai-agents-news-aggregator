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
