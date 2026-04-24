"""Production adapters for the YouTube pipeline."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import feedparser
from news_observability.logging import get_logger

from news_scraper.pipelines.adapters import VideoMetadata

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
