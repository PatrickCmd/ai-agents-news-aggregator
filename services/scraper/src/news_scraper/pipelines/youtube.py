"""YouTube pipeline — feedparser + transcript API → ArticleIn upsert."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol

from news_observability.logging import get_logger
from news_schemas.article import ArticleIn, SourceType
from news_schemas.scraper_run import (
    PipelineName,
    ScraperRunStatus,
    YouTubeStats,
)

from news_scraper.pipelines.adapters import (
    FetchedTranscript,
    TranscriptFetcher,
    VideoMetadata,
    YouTubeFeedFetcher,
)

_log = get_logger("youtube_pipeline")


class _ArticleRepo(Protocol):
    async def upsert_many(self, items: list[ArticleIn]) -> int: ...
    async def get_existing_external_ids(
        self, source_type: SourceType, external_ids: list[str]
    ) -> set[str]: ...


class YouTubePipeline:
    name = PipelineName.YOUTUBE

    def __init__(
        self,
        *,
        fetcher: YouTubeFeedFetcher,
        transcripts: TranscriptFetcher,
        repo: _ArticleRepo,
        channels: list[dict[str, str]],
        transcript_concurrency: int = 3,
    ) -> None:
        self._fetcher = fetcher
        self._transcripts = transcripts
        self._repo = repo
        self._channels = channels
        self._transcript_concurrency = transcript_concurrency

    async def run(self, *, lookback_hours: int) -> YouTubeStats:
        t0 = perf_counter()
        cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)
        stats = YouTubeStats(status=ScraperRunStatus.SUCCESS)

        # Phase 1: fetch all RSS feeds in parallel, collect candidate (video, channel) pairs
        async def fetch_channel(ch: dict[str, str]) -> list[tuple[VideoMetadata, str]]:
            try:
                videos = await self._fetcher.list_recent_videos(ch["channel_id"])
            except Exception as exc:
                stats.errors.append({"channel_id": ch["channel_id"], "error": str(exc)})
                return []
            stats.fetched += len(videos)
            recent = [v for v in videos if v.published_at is not None and v.published_at >= cutoff]
            stats.skipped_old += len(videos) - len(recent)
            return [(v, ch["name"]) for v in recent]

        per_channel = await asyncio.gather(*(fetch_channel(c) for c in self._channels))
        candidates: list[tuple[VideoMetadata, str]] = [
            pair for sublist in per_channel for pair in sublist
        ]

        # Phase 2: pre-filter against the DB so we don't re-fetch transcripts
        # for videos already stored from a previous overlapping ingest run.
        candidate_ids = [v.video_id for v, _ in candidates]
        existing = await self._repo.get_existing_external_ids(SourceType.YOUTUBE, candidate_ids)
        new_candidates = [(v, name) for v, name in candidates if v.video_id not in existing]
        stats.skipped_already_stored = len(candidates) - len(new_candidates)

        # Phase 3: transcript fetch (rate-limited) only for genuinely new videos
        sem = asyncio.Semaphore(self._transcript_concurrency)
        seen: set[str] = set()
        articles: list[ArticleIn] = []

        async def process_video(v: VideoMetadata, channel_name: str) -> None:
            async with sem:
                transcript = await self._transcripts.fetch(v.video_id)
            if transcript.text is None:
                # No transcript -> skip the row entirely. Digest agents shouldn't
                # see content-less articles. The next ingest run will retry the
                # video if it's still in the channel's RSS window.
                stats.transcripts_failed += 1
                return
            article = self._to_article(v, channel_name, transcript)
            key = f"{article.source_name}::{article.external_id}"
            if key in seen:
                return
            seen.add(key)
            articles.append(article)
            stats.transcripts_fetched += 1

        await asyncio.gather(*(process_video(v, name) for v, name in new_candidates))

        # Phase 4: upsert
        stats.kept = len(articles)
        try:
            stats.inserted = await self._repo.upsert_many(articles)
        except Exception as exc:
            _log.exception("youtube upsert failed: {}", exc)
            stats.status = ScraperRunStatus.FAILED
            stats.errors.append({"stage": "upsert", "error": str(exc)})
        stats.duration_seconds = perf_counter() - t0
        return stats

    @staticmethod
    def _to_article(
        v: VideoMetadata, channel_name: str, transcript: FetchedTranscript
    ) -> ArticleIn:
        raw: dict[str, Any] = {
            "channel_id": v.channel_id,
            "thumbnail_url": v.thumbnail_url,
            "description": v.description,
            "transcript_segments": transcript.segments,
            "transcript_error": transcript.error,
            "has_transcript": transcript.text is not None,
        }
        return ArticleIn(
            source_type=SourceType.YOUTUBE,
            source_name=channel_name,
            external_id=v.video_id,
            title=v.title,
            url=v.url,  # type: ignore[arg-type]
            author=channel_name,
            published_at=v.published_at,
            content_text=transcript.text,
            tags=[],
            raw=raw,
        )
