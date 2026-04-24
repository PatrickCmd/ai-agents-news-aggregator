"""Spawns rss-mcp against openai_news RSS. Run: uv run pytest -m live."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from news_scraper.mcp_servers import create_rss_mcp_server
from news_scraper.pipelines.rss_adapters import MCPFeedFetcher


@pytest.mark.live
@pytest.mark.asyncio
async def test_openai_news_feed_returns_items() -> None:
    path = os.environ.get(
        "RSS_MCP_PATH",
        str(Path(__file__).resolve().parents[5] / "rss-mcp" / "dist" / "index.js"),
    )
    assert Path(path).exists(), f"rss-mcp dist missing at {path}"
    async with create_rss_mcp_server(path, timeout_seconds=60) as server:
        fetcher = MCPFeedFetcher(server)
        result = await fetcher.get_feed("https://openai.com/news/rss.xml", count=3)
    assert "items" in result
    assert isinstance(result["items"], list)
