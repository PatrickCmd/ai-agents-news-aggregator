from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make services/scheduler/lambda_handler.py importable.
_AGENT_ROOT = Path(__file__).resolve().parents[4]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def test_handler_dispatches_list_unsummarised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")  # short-circuit ssm

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    captured: dict[str, Any] = {}

    async def _fake(*, hours: int, limit: int) -> dict[str, Any]:
        captured["hours"] = hours
        captured["limit"] = limit
        return {"article_ids": [1, 2, 3]}

    monkeypatch.setattr("news_scheduler.handlers.list_unsummarised.run", _fake)

    out = lambda_handler.handler({"op": "list_unsummarised", "hours": 24, "limit": 200}, None)
    assert out == {"article_ids": [1, 2, 3]}
    assert captured == {"hours": 24, "limit": 200}


def test_handler_dispatches_list_active_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    async def _fake() -> dict[str, Any]:
        return {"user_ids": ["uuid1", "uuid2"]}

    monkeypatch.setattr("news_scheduler.handlers.list_active_users.run", _fake)

    out = lambda_handler.handler({"op": "list_active_users"}, None)
    assert out == {"user_ids": ["uuid1", "uuid2"]}


def test_handler_dispatches_list_new_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    async def _fake() -> dict[str, Any]:
        return {"digest_ids": [10, 20]}

    monkeypatch.setattr("news_scheduler.handlers.list_new_digests.run", _fake)

    out = lambda_handler.handler({"op": "list_new_digests"}, None)
    assert out == {"digest_ids": [10, 20]}


def test_handler_returns_failure_on_unknown_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    out = lambda_handler.handler({"op": "make_coffee"}, None)
    assert out["failed"] is True
    assert out["reason"] == "unknown_op"
    assert out["op"] == "make_coffee"


def test_handler_returns_failure_on_missing_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    out = lambda_handler.handler({}, None)
    assert out["failed"] is True
    assert out["reason"] == "malformed_event"
