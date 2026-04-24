"""Production adapters for the YouTube pipeline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import feedparser
from news_observability.logging import get_logger
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

from news_scraper.pipelines.adapters import FetchedTranscript, VideoMetadata

_log = get_logger("youtube_adapter")

_RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


class FeedparserYouTubeFeedFetcher:
    async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]:
        url = _RSS_URL_TEMPLATE.format(channel_id=channel_id)
        feed: Any = await asyncio.to_thread(feedparser.parse, url)
        if getattr(feed, "bozo", False):
            _log.warning("feed parse bozo for {}: {}", channel_id, feed.bozo_exception)
        return [self._parse_entry(e, channel_id) for e in feed.entries]

    @staticmethod
    def _parse_entry(entry: Any, channel_id: str) -> VideoMetadata:
        entry_id = getattr(entry, "id", None) or ""
        video_id = entry_id.split(":")[-1] if entry_id else ""
        pub = getattr(entry, "published_parsed", None)
        published_at = (
            datetime(pub[0], pub[1], pub[2], pub[3], pub[4], pub[5], tzinfo=UTC) if pub else None
        )
        description = getattr(entry, "summary", "") or ""
        thumbnail_url = None
        media_thumbnail = getattr(entry, "media_thumbnail", None)
        if media_thumbnail:
            thumbnail_url = media_thumbnail[0].get("url")
        return VideoMetadata(
            video_id=video_id,
            title=getattr(entry, "title", "") or "",
            url=getattr(entry, "link", "") or "",
            channel_id=channel_id,
            published_at=published_at,
            description=description,
            thumbnail_url=thumbnail_url,
        )


class YouTubeTranscriptApiFetcher:
    def __init__(
        self,
        *,
        proxy_enabled: bool,
        proxy_username: str = "",
        proxy_password: str = "",
    ) -> None:
        self._proxy_enabled = proxy_enabled and bool(proxy_username) and bool(proxy_password)
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password

    async def fetch(self, video_id: str, languages: list[str] | None = None) -> FetchedTranscript:
        return await asyncio.to_thread(self._fetch_sync, video_id, languages or ["en"])

    def _fetch_sync(self, video_id: str, languages: list[str]) -> FetchedTranscript:
        try:
            api = self._build_api()
            fetched = api.fetch(video_id, languages=languages)
            segments = fetched.to_raw_data()
            full_text = TextFormatter().format_transcript(fetched)
            return FetchedTranscript(text=full_text, segments=segments, error=None)
        except Exception as exc:
            _log.info("transcript fetch failed for {}: {}", video_id, exc)
            return FetchedTranscript(text=None, segments=None, error=str(exc))

    def _build_api(self) -> Any:
        if self._proxy_enabled:
            from youtube_transcript_api.proxies import WebshareProxyConfig

            return YouTubeTranscriptApi(
                proxy_config=WebshareProxyConfig(
                    proxy_username=self._proxy_username,
                    proxy_password=self._proxy_password,
                )
            )
        return YouTubeTranscriptApi()
