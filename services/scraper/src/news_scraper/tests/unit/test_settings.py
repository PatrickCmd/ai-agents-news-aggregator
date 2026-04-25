from __future__ import annotations

import pytest

from news_scraper.settings import ScraperSettings


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "RSS_MCP_PATH",
        "WEB_SEARCH_MAX_TURNS",
        "WEB_SEARCH_SITE_TIMEOUT",
        "YOUTUBE_TRANSCRIPT_CONCURRENCY",
        "RSS_FEED_CONCURRENCY",
        "WEB_SEARCH_SITE_CONCURRENCY",
    ):
        monkeypatch.delenv(k, raising=False)
    s = ScraperSettings()
    assert s.rss_mcp_path == "/app/rss-mcp/dist/index.js"
    assert s.web_search_max_turns == 15
    assert s.web_search_site_timeout == 120
    assert s.youtube_transcript_concurrency == 3
    assert s.rss_feed_concurrency == 5
    assert s.web_search_site_concurrency == 2


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RSS_FEED_CONCURRENCY", "10")
    monkeypatch.setenv("WEB_SEARCH_MAX_TURNS", "8")
    s = ScraperSettings()
    assert s.rss_feed_concurrency == 10
    assert s.web_search_max_turns == 8
