from __future__ import annotations

from pathlib import Path

import pytest

from news_scraper.mcp_servers import _playwright_args, _rss_mcp_params


def test_rss_mcp_params_builds_node_command(tmp_path: Path) -> None:
    fake = tmp_path / "index.js"
    fake.write_text("// stub")
    params = _rss_mcp_params(str(fake))
    assert params["command"] == "node"
    assert params["args"] == [str(fake)]


def test_playwright_args_contain_hardening_flags() -> None:
    args = _playwright_args(docker=False)
    assert "--headless" in args
    assert "--isolated" in args
    assert "--no-sandbox" in args
    assert "--ignore-https-errors" in args
    assert "--user-agent" in args


def test_playwright_args_in_docker_add_executable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chrome_dir = tmp_path / "ms-playwright" / "chromium-9999" / "chrome-linux"
    chrome_dir.mkdir(parents=True)
    chrome = chrome_dir / "chrome"
    chrome.write_text("#!/bin/bash")
    monkeypatch.setattr(
        "news_scraper.mcp_servers._find_chromium",
        lambda: str(chrome),
    )
    args = _playwright_args(docker=True)
    assert "--executable-path" in args
    i = args.index("--executable-path")
    assert args[i + 1] == str(chrome)
