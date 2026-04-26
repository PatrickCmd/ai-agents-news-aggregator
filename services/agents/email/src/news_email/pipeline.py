"""Email pipeline — compose intro + send via Resend + record."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from agents import Runner, trace
from news_observability.audit import AuditLogger
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.validators import StructuredOutputError, validate_structured_output
from news_schemas.agent_io import EmailIntroduction
from news_schemas.audit import AgentName, AuditLogIn, DecisionType
from news_schemas.digest import DigestOut, DigestStatus
from news_schemas.email_send import EmailSendIn, EmailSendOut, EmailSendStatus
from news_schemas.user_profile import UserOut

from news_email.agent import build_agent, build_email_prompt
from news_email.render import render_digest_html

_log = get_logger("email_pipeline")
AuditWriter = Callable[[AuditLogIn], Awaitable[None]]
ResendSend = Callable[..., Awaitable[dict[str, Any]]]


class _UserRepo(Protocol):
    async def get_by_id(self, user_id: UUID) -> UserOut | None: ...


class _DigestRepo(Protocol):
    async def get_by_id(self, digest_id: int) -> DigestOut | None: ...
    async def update_status(
        self, digest_id: int, status: DigestStatus, error: str | None = None
    ) -> DigestOut: ...


class _EmailRepo(Protocol):
    async def get_sent_for_digest(self, digest_id: int) -> EmailSendOut | None: ...
    async def create(self, item: EmailSendIn) -> EmailSendOut: ...
    async def mark_sent(self, send_id: int, provider_message_id: str) -> EmailSendOut: ...
    async def mark_failed(self, send_id: int, error: str) -> EmailSendOut: ...


async def send_digest_email(
    *,
    digest_id: int,
    user_repo: _UserRepo,
    digest_repo: _DigestRepo,
    email_send_repo: _EmailRepo,
    audit_writer: AuditWriter,
    resend_send: ResendSend,
    model: str,
    sender_name: str,
    mail_from: str,
    mail_to_default: str,
    preview_only: bool = False,
) -> dict[str, Any]:
    """Compose + send the digest email. Idempotent.

    Behaviour paths:
        1. digest not found → return ``{"error": "digest not found", ...}``.
        2. user not found → return ``{"error": "user not found", ...}``.
        3. existing SENT email_send row → skip LLM + Resend, return existing id.
        4. preview_only=True → render and return HTML, no DB write, no send.
        5. validation failure → audit row, return ``{"failed": True, "reason": "validation"}``.
        6. happy path → compose, send, mark sent, flip digest status, audit.
        7. Resend error → mark email_send failed, re-raise (caller decides retry).
    """
    digest = await digest_repo.get_by_id(digest_id)
    if digest is None:
        _log.info("email skip: digest {} not found", digest_id)
        return {"error": "digest not found", "digest_id": digest_id}

    user = await user_repo.get_by_id(digest.user_id)
    if user is None:
        _log.info("email skip: user {} not found for digest {}", digest.user_id, digest_id)
        return {"error": "user not found", "digest_id": digest_id}

    if not preview_only:
        existing = await email_send_repo.get_sent_for_digest(digest_id)
        if existing:
            _log.info(
                "email skip: digest {} already emailed (send_id={})",
                digest_id,
                existing.id,
            )
            return {"email_send_id": existing.id, "skipped": True}

    agent = build_agent(model=model)
    ranked_payload = [
        {
            "title": r.title,
            "summary": r.summary,
            "why_ranked": r.why_ranked,
            "score": r.score,
        }
        for r in digest.ranked_articles
    ]
    prompt = build_email_prompt(
        email_name=user.email_name,
        top_themes=digest.top_themes,
        ranked=ranked_payload,
    )

    t0 = perf_counter()
    with trace(f"email.digest.{digest_id}"):
        result = await Runner.run(agent, input=prompt)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    audit = AuditLogger(audit_writer)
    usage = extract_usage(result, model=model)

    try:
        intro = validate_structured_output(EmailIntroduction, result.final_output)
    except StructuredOutputError as exc:
        _log.error("email validation_failed for digest {}: {}", digest_id, exc)
        await audit.log_decision(
            agent_name=AgentName.EMAIL,
            user_id=user.id,
            decision_type=DecisionType.INTRO,
            input_text=f"digest {digest_id} for {user.email_name}",
            output_text="validation_failed",
            metadata={
                "digest_id": digest_id,
                "model": usage.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "requests": usage.requests,
                "estimated_cost_usd": usage.estimated_cost_usd,
                "duration_ms": elapsed_ms,
                "error": str(exc),
            },
        )
        return {"digest_id": digest_id, "failed": True, "reason": "validation"}

    html = render_digest_html(intro, digest.ranked_articles, digest.top_themes)

    if preview_only:
        return {
            "html": html,
            "subject": intro.subject_line,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        }

    to_address = mail_to_default or user.email
    send_row = await email_send_repo.create(
        EmailSendIn(
            user_id=user.id,
            digest_id=digest_id,
            to_address=to_address,
            subject=intro.subject_line,
            status=EmailSendStatus.PENDING,
        )
    )

    try:
        resp = await resend_send(
            to=to_address,
            subject=intro.subject_line,
            html=html,
            sender_name=sender_name,
            mail_from=mail_from,
        )
    except Exception as exc:
        await email_send_repo.mark_failed(send_row.id, error=str(exc))
        raise

    provider_id = str(resp.get("id", ""))
    await email_send_repo.mark_sent(send_row.id, provider_message_id=provider_id)
    await digest_repo.update_status(digest_id, DigestStatus.EMAILED)

    await audit.log_decision(
        agent_name=AgentName.EMAIL,
        user_id=user.id,
        decision_type=DecisionType.INTRO,
        input_text=f"digest {digest_id} for {user.email_name}",
        output_text=intro.introduction,
        metadata={
            "digest_id": digest_id,
            "email_send_id": send_row.id,
            "provider_message_id": provider_id,
            "subject": intro.subject_line,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "requests": usage.requests,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "duration_ms": elapsed_ms,
        },
    )

    _log.info(
        "email ok: digest {} sent (msg={}, send_id={})",
        digest_id,
        provider_id,
        send_row.id,
    )

    return {
        "email_send_id": send_row.id,
        "provider_message_id": provider_id,
        "skipped": False,
    }
