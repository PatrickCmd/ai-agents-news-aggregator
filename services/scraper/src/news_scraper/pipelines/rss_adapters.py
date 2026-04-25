"""RSS adapter — wraps MCPServerStdio over rss-mcp."""

from __future__ import annotations

import json
from typing import Any, Protocol

from news_observability.logging import get_logger

_log = get_logger("rss_adapter")


class _MCPServer(Protocol):
    async def call_tool(self, name: str, args: dict[str, Any]) -> Any: ...


class MCPFeedFetcher:
    """Thin wrapper around an MCPServerStdio-backed session calling get_feed."""

    def __init__(self, server: _MCPServer) -> None:
        self._server = server

    async def get_feed(self, url: str, count: int = 15) -> dict[str, Any]:
        result = await self._server.call_tool("get_feed", {"url": url, "count": count})
        is_error = getattr(result, "isError", False) or getattr(result, "is_error", False)
        if is_error:
            err = result.content[0].text if result.content else "unknown error"
            raise RuntimeError(f"get_feed error: {err}")
        if not result.content:
            raise ValueError("Empty response from get_feed")
        text = result.content[0].text
        return json.loads(text)  # type: ignore[no-any-return]
