from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from news_schemas.agent_io import EmailIntroduction
from news_schemas.audit import AuditLogIn
from news_schemas.digest import DigestOut, DigestStatus, RankedArticle
from news_schemas.email_send import EmailSendIn, EmailSendOut, EmailSendStatus
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserOut,
    UserProfile,
)


@dataclass
class _Usage:
    input_tokens: int = 50
    output_tokens: int = 30
    total_tokens: int = 80
    requests: int = 1


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: object
    context_wrapper: _Wrapper


def _profile() -> UserProfile:
    return UserProfile(
        background=[],
        interests=Interests(),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


def _user(uid: UUID) -> UserOut:
    return UserOut(
        id=uid,
        clerk_user_id="c",
        email="t@example.com",
        name="t",
        email_name="Pat",
        profile=_profile(),
        profile_completed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _digest(did: int, uid: UUID) -> DigestOut:
    return DigestOut(
        id=did,
        user_id=uid,
        period_start=datetime.now(UTC) - timedelta(hours=24),
        period_end=datetime.now(UTC),
        intro=None,
        ranked_articles=[
            RankedArticle(
                article_id=1,
                score=80,
                title="T",
                url="https://x/1",
                summary="S",
                why_ranked="ten chars long",
            )
        ],
        top_themes=["agents"],
        article_count=1,
        status=DigestStatus.GENERATED,
        error_message=None,
        generated_at=datetime.now(UTC),
    )


def _intro() -> EmailIntroduction:
    return EmailIntroduction(
        greeting="Hi Pat,",
        introduction="Welcome to today's digest, lots happening!",
        highlight="The biggest story is the SDK GA.",
        subject_line="AI Daily — agents go GA",
    )


class _UserRepo:
    def __init__(self, u: UserOut | None) -> None:
        self._u = u

    async def get_by_id(self, uid: UUID) -> UserOut | None:
        return self._u


class _DigestRepo:
    def __init__(self, d: DigestOut | None) -> None:
        self._d = d
        self.status_updates: list[tuple[int, DigestStatus]] = []

    async def get_by_id(self, did: int) -> DigestOut | None:
        return self._d

    async def update_status(
        self, digest_id: int, status: DigestStatus, error: str | None = None
    ) -> DigestOut:
        self.status_updates.append((digest_id, status))
        assert self._d is not None
        return self._d


class _EmailRepo:
    def __init__(self, *, sent_existing: EmailSendOut | None = None) -> None:
        self.sent_existing = sent_existing
        self.created: list[EmailSendIn] = []
        self.marked_sent: list[tuple[int, str]] = []
        self.marked_failed: list[tuple[int, str]] = []
        self._next_id = 200

    async def get_sent_for_digest(self, did: int) -> EmailSendOut | None:
        return self.sent_existing

    async def create(self, item: EmailSendIn) -> EmailSendOut:
        self.created.append(item)
        out = EmailSendOut(
            id=self._next_id,
            user_id=item.user_id,
            digest_id=item.digest_id,
            provider=item.provider,
            to_address=item.to_address,
            subject=item.subject,
            status=item.status,
            provider_message_id=item.provider_message_id,
            sent_at=item.sent_at,
            error_message=item.error_message,
        )
        self._next_id += 1
        return out

    async def mark_sent(self, sid: int, provider_message_id: str) -> EmailSendOut:
        self.marked_sent.append((sid, provider_message_id))
        return EmailSendOut(
            id=sid,
            user_id=uuid4(),
            digest_id=1,
            provider="resend",
            to_address="t@example.com",
            subject="s",
            status=EmailSendStatus.SENT,
            provider_message_id=provider_message_id,
            sent_at=datetime.now(UTC),
            error_message=None,
        )

    async def mark_failed(self, sid: int, error: str) -> EmailSendOut:
        self.marked_failed.append((sid, error))
        return EmailSendOut(
            id=sid,
            user_id=uuid4(),
            digest_id=1,
            provider="resend",
            to_address="t@example.com",
            subject="s",
            status=EmailSendStatus.FAILED,
            provider_message_id=None,
            sent_at=None,
            error_message=error,
        )


class _AuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditLogIn] = []

    async def insert(self, e: AuditLogIn) -> None:
        self.entries.append(e)


@pytest.mark.asyncio
async def test_send_digest_skips_when_already_sent() -> None:
    """Idempotency: existing SENT row → skip LLM + Resend, return existing send_id."""
    from news_email import pipeline

    uid = uuid4()
    sent_existing = EmailSendOut(
        id=999,
        user_id=uid,
        digest_id=1,
        provider="resend",
        to_address="t@example.com",
        subject="s",
        status=EmailSendStatus.SENT,
        provider_message_id="m",
        sent_at=datetime.now(UTC),
        error_message=None,
    )

    async def _should_not_be_called(**kw: Any) -> dict[str, Any]:
        raise AssertionError("resend should not be called when idempotent")

    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=_UserRepo(_user(uid)),
        digest_repo=_DigestRepo(_digest(1, uid)),
        email_send_repo=_EmailRepo(sent_existing=sent_existing),
        audit_writer=_AuditRepo().insert,
        resend_send=_should_not_be_called,
        model="gpt-5.4-mini",
        sender_name="x",
        mail_from="x@x",
        mail_to_default="",
    )
    assert out["email_send_id"] == 999
    assert out["skipped"] is True


@pytest.mark.asyncio
async def test_send_digest_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compose intro → render HTML → Resend send → mark_sent → flip digest status."""
    from news_email import pipeline

    uid = uuid4()
    digest = _digest(1, uid)

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    sends: list[dict[str, Any]] = []

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        sends.append(kwargs)
        return {"id": "msg-1"}

    user_repo = _UserRepo(_user(uid))
    digest_repo = _DigestRepo(digest)
    email_repo = _EmailRepo()
    audit = _AuditRepo()

    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=user_repo,
        digest_repo=digest_repo,
        email_send_repo=email_repo,
        audit_writer=audit.insert,
        resend_send=_fake_resend,
        model="gpt-5.4-mini",
        sender_name="AI News",
        mail_from="hi@news.example",
        mail_to_default="",
    )
    assert out["skipped"] is False
    assert sends and sends[0]["to"] == "t@example.com"
    assert email_repo.created
    assert email_repo.created[0].subject == "AI Daily — agents go GA"
    assert email_repo.marked_sent == [(200, "msg-1")]
    assert digest_repo.status_updates == [(1, DigestStatus.EMAILED)]
    assert audit.entries


@pytest.mark.asyncio
async def test_send_digest_marks_failed_on_resend_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resend 429 (typed): mark email_send failed, re-raise."""
    from news_email import pipeline
    from news_email.resend_client import ResendRateLimitError

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        raise ResendRateLimitError("Resend rate limit exceeded")

    email_repo = _EmailRepo()
    with pytest.raises(ResendRateLimitError):
        await pipeline.send_digest_email(
            digest_id=1,
            user_repo=_UserRepo(_user(uid)),
            digest_repo=_DigestRepo(_digest(1, uid)),
            email_send_repo=email_repo,
            audit_writer=_AuditRepo().insert,
            resend_send=_fake_resend,
            model="gpt-5.4-mini",
            sender_name="x",
            mail_from="x@x",
            mail_to_default="",
        )
    assert email_repo.marked_failed
    assert "rate limit" in email_repo.marked_failed[0][1]


@pytest.mark.asyncio
async def test_send_digest_marks_failed_on_resend_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resend 422 (typed): mark email_send failed, re-raise."""
    from news_email import pipeline
    from news_email.resend_client import ResendValidationError

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        raise ResendValidationError("Resend validation error: bad from")

    email_repo = _EmailRepo()
    with pytest.raises(ResendValidationError):
        await pipeline.send_digest_email(
            digest_id=1,
            user_repo=_UserRepo(_user(uid)),
            digest_repo=_DigestRepo(_digest(1, uid)),
            email_send_repo=email_repo,
            audit_writer=_AuditRepo().insert,
            resend_send=_fake_resend,
            model="gpt-5.4-mini",
            sender_name="x",
            mail_from="x@x",
            mail_to_default="",
        )
    assert email_repo.marked_failed


@pytest.mark.asyncio
async def test_preview_only_returns_html_no_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """preview_only=True: render HTML, return it, no Resend, no DB write."""
    from news_email import pipeline

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    sent_called = False

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        nonlocal sent_called
        sent_called = True
        return {"id": "x"}

    email_repo = _EmailRepo()
    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=_UserRepo(_user(uid)),
        digest_repo=_DigestRepo(_digest(1, uid)),
        email_send_repo=email_repo,
        audit_writer=_AuditRepo().insert,
        resend_send=_fake_resend,
        model="gpt-5.4-mini",
        sender_name="x",
        mail_from="x@x",
        mail_to_default="",
        preview_only=True,
    )
    assert "Hi Pat," in out["html"]
    assert sent_called is False
    assert email_repo.created == []


@pytest.mark.asyncio
async def test_send_digest_handles_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §9: structured-output validation failure is a business failure.

    Audit row written with output_summary='validation_failed';
    return dict has failed=True; no DB write of email_send; no Resend call.
    """
    from news_email import pipeline

    uid = uuid4()

    # Garbage that fails EmailIntroduction validation: greeting too short.
    bad_output = {
        "greeting": "Hi",  # min_length=5
        "introduction": "x" * 30,
        "highlight": "x" * 20,
        "subject_line": "x" * 10,
    }

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(bad_output, _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    sent_called = False

    async def _fake_resend(**kwargs: Any) -> dict[str, Any]:
        nonlocal sent_called
        sent_called = True
        return {"id": "x"}

    email_repo = _EmailRepo()
    audit = _AuditRepo()
    out = await pipeline.send_digest_email(
        digest_id=1,
        user_repo=_UserRepo(_user(uid)),
        digest_repo=_DigestRepo(_digest(1, uid)),
        email_send_repo=email_repo,
        audit_writer=audit.insert,
        resend_send=_fake_resend,
        model="gpt-5.4-mini",
        sender_name="x",
        mail_from="x@x",
        mail_to_default="",
    )
    assert out["failed"] is True
    assert out["reason"] == "validation"
    assert sent_called is False
    assert email_repo.created == []
    assert any(e.output_summary == "validation_failed" for e in audit.entries)


@pytest.mark.asyncio
async def test_send_digest_does_not_catch_programmer_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TypeError from a buggy resend_send must propagate cleanly.

    Should NOT be caught and serialised into email_send.error_message
    — that would be misleading garbage in the FAILED row.
    """
    from news_email import pipeline

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    async def _buggy_resend(**kwargs: Any) -> dict[str, Any]:
        raise TypeError("a programmer bug, not a Resend error")

    email_repo = _EmailRepo()
    with pytest.raises(TypeError):
        await pipeline.send_digest_email(
            digest_id=1,
            user_repo=_UserRepo(_user(uid)),
            digest_repo=_DigestRepo(_digest(1, uid)),
            email_send_repo=email_repo,
            audit_writer=_AuditRepo().insert,
            resend_send=_buggy_resend,
            model="gpt-5.4-mini",
            sender_name="x",
            mail_from="x@x",
            mail_to_default="",
        )
    # mark_failed must NOT be called — this isn't a Resend failure
    assert email_repo.marked_failed == []


@pytest.mark.asyncio
async def test_send_digest_hard_fails_when_resend_returns_no_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resend returning 200 but no id → ResendError, mark_failed, raise."""
    from news_email import pipeline
    from news_email.resend_client import ResendError

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    async def _no_id_resend(**kwargs: Any) -> dict[str, Any]:
        return {}  # no "id" key

    email_repo = _EmailRepo()
    with pytest.raises(ResendError, match="no id"):
        await pipeline.send_digest_email(
            digest_id=1,
            user_repo=_UserRepo(_user(uid)),
            digest_repo=_DigestRepo(_digest(1, uid)),
            email_send_repo=email_repo,
            audit_writer=_AuditRepo().insert,
            resend_send=_no_id_resend,
            model="gpt-5.4-mini",
            sender_name="x",
            mail_from="x@x",
            mail_to_default="",
        )
    # mark_failed should be called
    assert email_repo.marked_failed
    assert "no id" in email_repo.marked_failed[0][1]
    # mark_sent should NOT be called
    assert email_repo.marked_sent == []


@pytest.mark.asyncio
async def test_send_digest_marks_failed_on_httpx_request_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport errors (httpx.RequestError subclasses) get caught + mark_failed + re-raise.

    Note: real callers will wrap with `retry_transient` upstream, but the
    pipeline must still surface a final failure cleanly if retries exhaust.
    """
    import httpx

    from news_email import pipeline

    uid = uuid4()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(_intro(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_email.pipeline.Runner.run", _fake_runner_run)

    async def _timeout_resend(**kwargs: Any) -> dict[str, Any]:
        raise httpx.ReadTimeout("connection timed out")

    email_repo = _EmailRepo()
    with pytest.raises(httpx.ReadTimeout):
        await pipeline.send_digest_email(
            digest_id=1,
            user_repo=_UserRepo(_user(uid)),
            digest_repo=_DigestRepo(_digest(1, uid)),
            email_send_repo=email_repo,
            audit_writer=_AuditRepo().insert,
            resend_send=_timeout_resend,
            model="gpt-5.4-mini",
            sender_name="x",
            mail_from="x@x",
            mail_to_default="",
        )
    assert email_repo.marked_failed
    assert "timed out" in email_repo.marked_failed[0][1]
