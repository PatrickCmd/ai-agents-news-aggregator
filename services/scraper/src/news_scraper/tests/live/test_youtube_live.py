"""Hits YouTube RSS for one channel. Run: uv run pytest -m live."""

from __future__ import annotations

import pytest

from news_scraper.pipelines.youtube_adapters import FeedparserYouTubeFeedFetcher


@pytest.mark.live
@pytest.mark.asyncio
async def test_real_channel_returns_video_metadata() -> None:
    fetcher = FeedparserYouTubeFeedFetcher()
    videos = await fetcher.list_recent_videos("UC_x5XG1OV2P6uZZ5FSM9Ttw")
    assert isinstance(videos, list)
    if videos:
        assert videos[0].video_id
        assert videos[0].url.startswith("https://")
