from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make services/agents/email/lambda_handler.py importable.
_AGENT_ROOT = Path(__file__).resolve().parents[4]
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))


def test_handler_invokes_pipeline_with_digest_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler bridges Lambda's sync invocation to our async pipeline."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")  # short-circuit ssm

    captured: dict[str, Any] = {}

    async def _fake_pipeline(
        *,
        digest_id: int,
        user_repo: object,
        digest_repo: object,
        email_send_repo: object,
        audit_writer: object,
        resend_send: object,
        model: str,
        sender_name: str,
        mail_from: str,
        mail_to_default: str,
    ) -> dict[str, Any]:
        captured["digest_id"] = digest_id
        return {"email_send_id": 7, "skipped": False}

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    def _fake_get_session() -> _FakeSession:
        return _FakeSession()

    # Clear any cached lambda_handler from a prior test (digest/editor's handler
    # has the same module name and pollutes sys.modules).
    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    monkeypatch.setattr("news_email.pipeline.send_digest_email", _fake_pipeline)
    monkeypatch.setattr(lambda_handler, "get_session", _fake_get_session)
    monkeypatch.setattr("news_db.repositories.user_repo.UserRepository", lambda s: object())
    monkeypatch.setattr("news_db.repositories.digest_repo.DigestRepository", lambda s: object())
    monkeypatch.setattr(
        "news_db.repositories.email_send_repo.EmailSendRepository", lambda s: object()
    )
    monkeypatch.setattr(
        "news_db.repositories.audit_log_repo.AuditLogRepository",
        lambda s: type("R", (), {"insert": lambda self, e: None})(),
    )

    out = lambda_handler.handler({"digest_id": 17}, None)
    assert out["email_send_id"] == 7
    assert captured["digest_id"] == 17


def test_handler_returns_failure_dict_on_malformed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed events return structured failure dict, not raise."""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")

    sys.modules.pop("lambda_handler", None)
    if sys.path[0] != str(_AGENT_ROOT):
        sys.path.insert(0, str(_AGENT_ROOT))
    import lambda_handler

    out_missing = lambda_handler.handler({}, None)
    assert out_missing["failed"] is True
    assert out_missing["reason"] == "malformed_event"

    out_bad_int = lambda_handler.handler({"digest_id": "not-a-number"}, None)
    assert out_bad_int["failed"] is True
    assert out_bad_int["reason"] == "malformed_event"
