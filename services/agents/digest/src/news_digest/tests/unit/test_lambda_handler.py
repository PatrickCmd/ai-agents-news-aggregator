from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make services/agents/digest/lambda_handler.py importable.
_AGENT_ROOT = Path(__file__).resolve().parents[4]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def test_handler_invokes_pipeline_with_article_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler bridges Lambda's sync invocation to our async pipeline."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")  # short-circuit ssm

    captured: dict[str, Any] = {}

    async def _fake_pipeline(
        *,
        article_id: int,
        article_repo: object,
        audit_writer: object,
        model: str,
        max_content_chars: int,
    ) -> dict[str, Any]:
        captured["article_id"] = article_id
        captured["model"] = model
        return {"article_id": article_id, "skipped": False}

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    def _fake_get_session() -> _FakeSession:
        return _FakeSession()

    # Import lambda_handler module after env is patched.
    import lambda_handler

    monkeypatch.setattr("news_digest.pipeline.summarize_article", _fake_pipeline)
    monkeypatch.setattr(lambda_handler, "get_session", _fake_get_session)
    monkeypatch.setattr("news_db.repositories.article_repo.ArticleRepository", lambda s: object())
    monkeypatch.setattr(
        "news_db.repositories.audit_log_repo.AuditLogRepository",
        lambda s: type("R", (), {"insert": lambda self, e: None})(),
    )

    out = lambda_handler.handler({"article_id": 42}, None)
    assert out["article_id"] == 42
    assert captured["article_id"] == 42
