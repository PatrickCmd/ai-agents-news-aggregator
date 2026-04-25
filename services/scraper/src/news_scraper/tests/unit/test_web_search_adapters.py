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
            items=[WebSearchItem(title="Post 1", url="https://replit.com/blog/post-1")],
        ),
        context_wrapper=_Wrapper(usage=_Usage()),
    )

    async def _fake_runner_run(agent: object, input: str, max_turns: int) -> _FakeResult:  # noqa: A002
        return fake_result

    class _FakeMCP:
        async def __aenter__(self) -> _FakeMCP:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    def _fake_factory(*, timeout_seconds: int) -> _FakeMCP:
        return _FakeMCP()

    monkeypatch.setattr(
        "news_scraper.pipelines.web_search_adapters.Runner.run",
        _fake_runner_run,
    )
    monkeypatch.setattr(
        "news_scraper.pipelines.web_search_adapters.create_playwright_mcp_server",
        _fake_factory,
    )

    crawler = PlaywrightAgentCrawler(model="gpt-5.4-mini", max_turns=5, site_timeout=30)
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
