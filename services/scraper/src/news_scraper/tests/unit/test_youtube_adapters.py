from __future__ import annotations

import types
from datetime import UTC, datetime

import pytest

from news_scraper.pipelines.youtube_adapters import FeedparserYouTubeFeedFetcher


def _fake_parse_factory(entries: list[dict]):
    def _fake_parse(url: str):
        return types.SimpleNamespace(
            bozo=False,
            bozo_exception=None,
            entries=[types.SimpleNamespace(**e) for e in entries],
        )

    return _fake_parse


@pytest.mark.asyncio
async def test_list_recent_videos_parses_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_parse = _fake_parse_factory(
        [
            {
                "id": "yt:video:abc123",
                "title": "Hello",
                "link": "https://www.youtube.com/watch?v=abc123",
                "published_parsed": (2026, 4, 24, 10, 0, 0, 0, 0, 0),
                "summary": "desc",
            }
        ]
    )
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.feedparser.parse",
        fake_parse,
    )
    fetcher = FeedparserYouTubeFeedFetcher()
    videos = await fetcher.list_recent_videos("UC_test")
    assert len(videos) == 1
    assert videos[0].video_id == "abc123"
    assert videos[0].published_at == datetime(2026, 4, 24, 10, 0, 0, tzinfo=UTC)
    assert videos[0].channel_id == "UC_test"


@pytest.mark.asyncio
async def test_list_recent_videos_handles_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_parse = _fake_parse_factory([{"id": "yt:video:xyz", "title": "t", "link": "https://u"}])
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.feedparser.parse",
        fake_parse,
    )
    fetcher = FeedparserYouTubeFeedFetcher()
    videos = await fetcher.list_recent_videos("UC_test")
    assert videos[0].video_id == "xyz"
    assert videos[0].published_at is None
    assert videos[0].description == ""


@pytest.mark.asyncio
async def test_empty_feed_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.feedparser.parse",
        _fake_parse_factory([]),
    )
    fetcher = FeedparserYouTubeFeedFetcher()
    assert await fetcher.list_recent_videos("UC_test") == []
