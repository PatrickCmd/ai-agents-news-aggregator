"""RSS pipeline — fetch via rss-mcp, normalize, upsert."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol

from dateutil import parser as date_parser
from news_config.loader import RSSFeedConfig
from news_observability.logging import get_logger
from news_schemas.article import ArticleIn, SourceType
from news_schemas.scraper_run import PipelineName, PipelineStats, ScraperRunStatus

from news_scraper.pipelines.adapters import FeedFetcher

_log = get_logger("rss_pipeline")


class _ArticleRepo(Protocol):
    async def upsert_many(self, items: list[ArticleIn]) -> int: ...


def _parse_pub_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt: datetime = date_parser.parse(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _stable_dedup_key(item: dict[str, Any]) -> str:
    if item.get("guid"):
        return str(item["guid"])
    if item.get("link"):
        return str(item["link"])
    fingerprint = f"{item.get('title', '')}|{item.get('pubDate', '')}"
    return "sha256:" + hashlib.sha256(fingerprint.encode()).hexdigest()


class RSSPipeline:
    name = PipelineName.RSS

    def __init__(
        self,
        *,
        fetcher: FeedFetcher,
        repo: _ArticleRepo,
        feeds: list[RSSFeedConfig],
        feed_concurrency: int = 5,
    ) -> None:
        self._fetcher = fetcher
        self._repo = repo
        self._feeds = feeds
        self._feed_concurrency = feed_concurrency

    async def run(self, *, lookback_hours: int) -> PipelineStats:
        t0 = perf_counter()
        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        stats = PipelineStats(status=ScraperRunStatus.SUCCESS)
        sem = asyncio.Semaphore(self._feed_concurrency)
        seen: set[str] = set()
        articles: list[ArticleIn] = []

        async def process_feed(feed: RSSFeedConfig) -> None:
            async with sem:
                try:
                    payload = await self._fetcher.get_feed(str(feed.url))
                except Exception as exc:
                    stats.errors.append({"feed": feed.name, "error": str(exc)})
                    return
            for item in payload.get("items", []):
                stats.fetched += 1
                pub = _parse_pub_date(item.get("pubDate"))
                if pub is None or pub < cutoff:
                    stats.skipped_old += 1
                    continue
                key = _stable_dedup_key(item)
                marker = f"{feed.name}::{key}"
                if marker in seen:
                    continue
                seen.add(marker)
                link = item.get("link")
                if not link:
                    stats.errors.append({"feed": feed.name, "guid": key, "error": "missing link"})
                    continue
                articles.append(
                    ArticleIn(
                        source_type=SourceType.RSS,
                        source_name=feed.name,
                        external_id=key,
                        title=item.get("title") or "(untitled)",
                        url=link,
                        author=item.get("author"),
                        published_at=pub,
                        content_text=item.get("description"),
                        tags=list(item.get("category") or []),
                        raw=item,
                    )
                )

        await asyncio.gather(*(process_feed(f) for f in self._feeds))
        stats.kept = len(articles)

        if stats.errors and stats.kept == 0:
            stats.status = ScraperRunStatus.FAILED
        else:
            try:
                stats.inserted = await self._repo.upsert_many(articles)
            except Exception as exc:
                _log.exception("rss upsert failed: {}", exc)
                stats.status = ScraperRunStatus.FAILED
                stats.errors.append({"stage": "upsert", "error": str(exc)})

        stats.duration_seconds = perf_counter() - t0
        return stats
