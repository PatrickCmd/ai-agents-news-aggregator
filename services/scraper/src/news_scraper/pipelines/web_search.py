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
            url=str(item.url),  # type: ignore[arg-type]
            author=item.author,
            published_at=item.published_at,
            content_text=item.summary,
            tags=[],
            raw={"extracted_by": "web_search_agent"},
        )
