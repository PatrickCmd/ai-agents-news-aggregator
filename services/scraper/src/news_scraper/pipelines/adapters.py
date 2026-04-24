"""Adapter boundaries — every MCP/network call goes through these Protocols.

Unit tests inject fakes; production wires the MCP/feedparser-backed impls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from news_config.loader import WebSearchSiteConfig
from pydantic import BaseModel, Field, HttpUrl

# -------- YouTube adapter types --------


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str
    title: str
    url: str
    channel_id: str
    published_at: datetime | None
    description: str
    thumbnail_url: str | None


@dataclass(frozen=True)
class FetchedTranscript:
    text: str | None
    segments: list[dict[str, Any]] | None
    error: str | None


class YouTubeFeedFetcher(Protocol):
    async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]: ...


class TranscriptFetcher(Protocol):
    async def fetch(
        self, video_id: str, languages: list[str] | None = None
    ) -> FetchedTranscript: ...


# -------- RSS adapter --------


class FeedFetcher(Protocol):
    async def get_feed(self, url: str, count: int = 15) -> dict[str, Any]: ...


# -------- Web-search adapter types --------


class WebSearchItem(BaseModel):
    title: str = Field(..., min_length=1)
    url: HttpUrl
    author: str | None = None
    published_at: datetime | None = None
    summary: str | None = Field(default=None, max_length=2000)


class SiteCrawlResult(BaseModel):
    site_name: str
    items: list[WebSearchItem] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class CrawlOutcome:
    result: SiteCrawlResult
    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int
    cost_usd: float | None
    duration_ms: int


class WebCrawler(Protocol):
    async def crawl_site(
        self, site: WebSearchSiteConfig, *, lookback_hours: int
    ) -> CrawlOutcome: ...
