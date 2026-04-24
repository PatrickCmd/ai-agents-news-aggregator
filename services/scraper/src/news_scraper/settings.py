"""Scraper-specific settings, extending the AppSettings baseline."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScraperSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    rss_mcp_path: str = Field(default="/app/rss-mcp/dist/index.js", alias="RSS_MCP_PATH")
    web_search_max_turns: int = Field(default=15, alias="WEB_SEARCH_MAX_TURNS")
    web_search_site_timeout: int = Field(default=120, alias="WEB_SEARCH_SITE_TIMEOUT")
    youtube_transcript_concurrency: int = Field(default=3, alias="YOUTUBE_TRANSCRIPT_CONCURRENCY")
    rss_feed_concurrency: int = Field(default=5, alias="RSS_FEED_CONCURRENCY")
    web_search_site_concurrency: int = Field(default=2, alias="WEB_SEARCH_SITE_CONCURRENCY")
