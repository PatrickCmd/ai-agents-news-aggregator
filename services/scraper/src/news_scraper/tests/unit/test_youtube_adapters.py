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


@pytest.mark.asyncio
async def test_transcript_fetcher_returns_text_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scraper.pipelines.youtube_adapters import YouTubeTranscriptApiFetcher

    class _FakeAPI:
        def __init__(self, proxy_config: object = None) -> None:
            pass

        def fetch(self, video_id: str, languages: list[str]) -> object:
            return types.SimpleNamespace(
                to_raw_data=lambda: [{"text": "hi", "start": 0.0, "duration": 1.0}]
            )

    def _fake_format(transcript: object) -> str:
        return "hi"

    monkeypatch.setattr("news_scraper.pipelines.youtube_adapters.YouTubeTranscriptApi", _FakeAPI)
    monkeypatch.setattr(
        "news_scraper.pipelines.youtube_adapters.TextFormatter",
        lambda: types.SimpleNamespace(format_transcript=_fake_format),
    )
    fetcher = YouTubeTranscriptApiFetcher(proxy_enabled=False)
    result = await fetcher.fetch("abc123")
    assert result.text == "hi"
    assert result.segments == [{"text": "hi", "start": 0.0, "duration": 1.0}]
    assert result.error is None


@pytest.mark.asyncio
async def test_transcript_fetcher_graceful_degradation_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scraper.pipelines.youtube_adapters import YouTubeTranscriptApiFetcher

    class _FakeAPI:
        def __init__(self, proxy_config: object = None) -> None:
            pass

        def fetch(self, video_id: str, languages: list[str]) -> object:
            raise RuntimeError("YouTube is blocking requests")

    monkeypatch.setattr("news_scraper.pipelines.youtube_adapters.YouTubeTranscriptApi", _FakeAPI)
    fetcher = YouTubeTranscriptApiFetcher(proxy_enabled=False)
    result = await fetcher.fetch("abc")
    assert result.text is None
    assert result.error is not None
    assert "blocking" in result.error.lower()
