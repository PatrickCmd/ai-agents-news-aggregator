from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

# Make services/agents/editor/lambda_handler.py importable.
_AGENT_ROOT = Path(__file__).resolve().parents[4]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def test_handler_invokes_pipeline_with_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handler bridges Lambda's sync invocation to our async pipeline."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")  # short-circuit ssm

    captured: dict[str, Any] = {}
    uid = uuid4()

    async def _fake_pipeline(
        *,
        user_id: object,
        article_repo: object,
        user_repo: object,
        digest_repo: object,
        audit_writer: object,
        model: str,
        lookback_hours: int,
        limit: int,
        top_n: int,
    ) -> dict[str, Any]:
        captured["user_id"] = user_id
        captured["lookback_hours"] = lookback_hours
        return {"digest_id": 7, "status": "generated"}

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    def _fake_get_session() -> _FakeSession:
        return _FakeSession()

    sys.modules.pop("lambda_handler", None)  # ensure fresh import
    # Ensure this agent's root is ahead of any sibling agent's root on sys.path
    # (sibling test files may have inserted their own root during collection).
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    monkeypatch.setattr("news_editor.pipeline.rank_for_user", _fake_pipeline)
    monkeypatch.setattr(lambda_handler, "get_session", _fake_get_session)
    monkeypatch.setattr("news_db.repositories.article_repo.ArticleRepository", lambda s: object())
    monkeypatch.setattr("news_db.repositories.user_repo.UserRepository", lambda s: object())
    monkeypatch.setattr("news_db.repositories.digest_repo.DigestRepository", lambda s: object())
    monkeypatch.setattr(
        "news_db.repositories.audit_log_repo.AuditLogRepository",
        lambda s: type("R", (), {"insert": lambda self, e: None})(),
    )

    out = lambda_handler.handler({"user_id": str(uid), "lookback_hours": 12}, None)
    assert out["digest_id"] == 7
    assert captured["user_id"] == uid
    assert captured["lookback_hours"] == 12


def test_handler_returns_failure_dict_on_malformed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed events return structured failure dict, not raise."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)  # ensure fresh import
    # Ensure this agent's root is ahead of any sibling agent's root on sys.path
    # (sibling test files may have inserted their own root during collection).
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    out_missing = lambda_handler.handler({}, None)
    assert out_missing["failed"] is True
    assert out_missing["reason"] == "malformed_event"

    out_bad_uuid = lambda_handler.handler({"user_id": "not-a-uuid"}, None)
    assert out_bad_uuid["failed"] is True
    assert out_bad_uuid["reason"] == "malformed_event"
