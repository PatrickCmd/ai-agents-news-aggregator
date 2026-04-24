from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from news_schemas.article import ArticleIn
from news_schemas.scraper_run import ScraperRunStatus

from news_scraper.pipelines.adapters import FetchedTranscript, VideoMetadata
from news_scraper.pipelines.youtube import YouTubePipeline


class _FakeFeedFetcher:
    def __init__(self, videos: dict[str, list[VideoMetadata]]) -> None:
        self._videos = videos

    async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]:
        return self._videos.get(channel_id, [])


class _FakeTranscriptFetcher:
    def __init__(self, *, result: FetchedTranscript) -> None:
        self._result = result

    async def fetch(self, video_id: str, languages: list[str] | None = None) -> FetchedTranscript:
        return self._result


class _CapturingArticleRepo:
    def __init__(self) -> None:
        self.received: list[ArticleIn] = []

    async def upsert_many(self, items: list[ArticleIn]) -> int:
        self.received.extend(items)
        return len(items)


@pytest.mark.asyncio
async def test_youtube_pipeline_keeps_recent_videos_only() -> None:
    now = datetime.now(UTC)
    videos = {
        "UC1": [
            VideoMetadata(
                video_id="v-old",
                title="old",
                url="https://www.youtube.com/watch?v=v-old",
                channel_id="UC1",
                published_at=now - timedelta(hours=48),
                description="",
                thumbnail_url=None,
            ),
            VideoMetadata(
                video_id="v-new",
                title="new",
                url="https://www.youtube.com/watch?v=v-new",
                channel_id="UC1",
                published_at=now - timedelta(hours=2),
                description="",
                thumbnail_url=None,
            ),
        ]
    }
    repo = _CapturingArticleRepo()
    pipeline = YouTubePipeline(
        fetcher=_FakeFeedFetcher(videos),
        transcripts=_FakeTranscriptFetcher(
            result=FetchedTranscript(text="t", segments=[], error=None)
        ),
        repo=repo,
        channels=[{"name": "chan", "channel_id": "UC1"}],
        transcript_concurrency=1,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert stats.status is ScraperRunStatus.SUCCESS
    assert stats.kept == 1
    assert stats.inserted == 1
    assert stats.transcripts_fetched == 1
    assert repo.received[0].external_id == "v-new"
    assert repo.received[0].content_text == "t"


@pytest.mark.asyncio
async def test_youtube_pipeline_records_transcript_failure_without_dropping_row() -> None:
    now = datetime.now(UTC)
    videos = {
        "UC1": [
            VideoMetadata(
                video_id="v1",
                title="v1",
                url="https://www.youtube.com/watch?v=v1",
                channel_id="UC1",
                published_at=now - timedelta(hours=1),
                description="",
                thumbnail_url=None,
            )
        ]
    }
    repo = _CapturingArticleRepo()
    pipeline = YouTubePipeline(
        fetcher=_FakeFeedFetcher(videos),
        transcripts=_FakeTranscriptFetcher(
            result=FetchedTranscript(text=None, segments=None, error="blocked")
        ),
        repo=repo,
        channels=[{"name": "c", "channel_id": "UC1"}],
        transcript_concurrency=1,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert stats.transcripts_failed == 1
    assert stats.kept == 1
    assert repo.received[0].content_text is None
    assert repo.received[0].raw["transcript_error"] == "blocked"


@pytest.mark.asyncio
async def test_youtube_pipeline_channel_error_isolated() -> None:
    class _ErrFetcher:
        async def list_recent_videos(self, channel_id: str) -> list[VideoMetadata]:
            if channel_id == "UC_bad":
                raise RuntimeError("boom")
            return []

    repo = _CapturingArticleRepo()
    pipeline = YouTubePipeline(
        fetcher=_ErrFetcher(),
        transcripts=_FakeTranscriptFetcher(
            result=FetchedTranscript(text=None, segments=None, error=None)
        ),
        repo=repo,
        channels=[
            {"name": "a", "channel_id": "UC_ok"},
            {"name": "b", "channel_id": "UC_bad"},
        ],
        transcript_concurrency=1,
    )
    stats = await pipeline.run(lookback_hours=24)
    assert len(stats.errors) == 1
    assert stats.errors[0]["channel_id"] == "UC_bad"
