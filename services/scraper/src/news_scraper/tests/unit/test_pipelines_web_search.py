from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from news_config.loader import WebSearchSiteConfig
from news_schemas.article import ArticleIn
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

    async def crawl_site(self, site: WebSearchSiteConfig, *, lookback_hours: int) -> CrawlOutcome:
        if site.name not in self._outcomes:
            raise RuntimeError(f"no fake outcome for {site.name}")
        return self._outcomes[site.name]


class _CapturingRepo:
    def __init__(self) -> None:
        self.received: list[ArticleIn] = []

    async def upsert_many(self, items: list[ArticleIn]) -> int:
        self.received.extend(items)
        return len(items)


class _CapturingAudit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def log_decision(self, **kwargs: object) -> None:
        self.records.append(dict(kwargs))


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
            WebSearchSiteConfig(
                name="ok_site",
                url="https://ok.example/blog",
                list_selector_hint="h",
            ),
            WebSearchSiteConfig(
                name="bad_site",
                url="https://bad.example/blog",
                list_selector_hint="h",
            ),
        ],
        site_concurrency=1,
        run_id=uuid4(),
    )
    stats = await pipeline.run(lookback_hours=48)
    assert stats.sites_attempted == 2
    assert stats.sites_succeeded == 1
    assert stats.status is ScraperRunStatus.PARTIAL
    assert any(e.get("site") == "bad_site" for e in stats.errors)
