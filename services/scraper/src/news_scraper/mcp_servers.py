"""MCP server factory functions.

Pattern follows alex-multi-agent-saas/backend/researcher/mcp_servers.py.
Returns configured MCPServerStdio instances ready for `async with` usage.
"""

from __future__ import annotations

import glob
import os
from typing import Any

from agents.mcp import MCPServerStdio

_PLAYWRIGHT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def _rss_mcp_params(path: str) -> dict[str, Any]:
    return {"command": "node", "args": [path]}


def _find_chromium() -> str | None:
    paths = glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
    return paths[0] if paths else None


def _in_docker() -> bool:
    return os.path.exists("/.dockerenv") or bool(os.environ.get("AWS_EXECUTION_ENV"))


def _playwright_args(*, docker: bool) -> list[str]:
    args: list[str] = [
        "@playwright/mcp@latest",
        "--headless",
        "--isolated",
        "--no-sandbox",
        "--ignore-https-errors",
        "--user-agent",
        _PLAYWRIGHT_USER_AGENT,
    ]
    if docker:
        chrome = _find_chromium()
        if chrome:
            args.extend(["--executable-path", chrome])
        else:
            args.extend(
                [
                    "--executable-path",
                    "/root/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
                ]
            )
    return args


def create_rss_mcp_server(path: str, *, timeout_seconds: int = 60) -> MCPServerStdio:
    """Spawn rss-mcp (Node) as a stdio MCP server. Use as `async with`.

    path: absolute path to rss-mcp/dist/index.js
    """
    return MCPServerStdio(
        name="rss-mcp",
        params=_rss_mcp_params(path),
        cache_tools_list=True,
        client_session_timeout_seconds=timeout_seconds,
    )


def create_playwright_mcp_server(*, timeout_seconds: int = 120) -> MCPServerStdio:
    """Spawn @playwright/mcp@latest as a stdio MCP server. Use as `async with`."""
    return MCPServerStdio(
        name="playwright-mcp",
        params={"command": "npx", "args": _playwright_args(docker=_in_docker())},
        cache_tools_list=True,
        client_session_timeout_seconds=timeout_seconds,
    )
