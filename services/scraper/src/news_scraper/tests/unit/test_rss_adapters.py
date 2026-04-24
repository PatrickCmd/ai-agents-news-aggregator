from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from news_scraper.pipelines.rss_adapters import MCPFeedFetcher


@dataclass
class _Content:
    text: str


@dataclass
class _ToolResult:
    content: list[_Content]
    isError: bool = False  # noqa: N815  — matches MCP CallToolResult JSON field


class _FakeServer:
    async def call_tool(self, name: str, args: dict) -> _ToolResult:
        payload = {"items": [{"title": "t", "link": "https://x"}]}
        return _ToolResult(content=[_Content(text=json.dumps(payload))])


@pytest.mark.asyncio
async def test_get_feed_returns_dict_from_mcp() -> None:
    fetcher = MCPFeedFetcher(_FakeServer())
    result = await fetcher.get_feed("https://example.com/rss")
    assert result["items"][0]["title"] == "t"


@pytest.mark.asyncio
async def test_get_feed_raises_on_tool_error() -> None:
    class _ErrServer:
        async def call_tool(self, name: str, args: dict) -> _ToolResult:
            return _ToolResult(content=[_Content(text="boom")], isError=True)

    fetcher = MCPFeedFetcher(_ErrServer())
    with pytest.raises(RuntimeError, match="boom"):
        await fetcher.get_feed("https://example.com/rss")


@pytest.mark.asyncio
async def test_get_feed_raises_on_empty_response() -> None:
    class _EmptyServer:
        async def call_tool(self, name: str, args: dict) -> _ToolResult:
            return _ToolResult(content=[])

    fetcher = MCPFeedFetcher(_EmptyServer())
    with pytest.raises(ValueError, match="Empty response"):
        await fetcher.get_feed("https://example.com/rss")
