"""Local Typer CLI for the email agent."""

from __future__ import annotations

import asyncio
import sys
from typing import Any, cast

import typer
from news_db.engine import get_session
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.email_send_repo import EmailSendRepository
from news_db.repositories.user_repo import UserRepository
from news_observability.logging import setup_logging
from news_observability.retry import retry_transient

from news_email.pipeline import ResendSend, send_digest_email
from news_email.resend_client import send_via_resend
from news_email.settings import EmailSettings

app = typer.Typer(no_args_is_help=True, help="Email agent CLI")


def _resend_send_factory(api_key: str) -> ResendSend:
    """Build a `resend_send` callable that closes over the api_key + retries.

    Wraps `send_via_resend` with `retry_transient` (4 attempts, exponential
    backoff) — only retries on transport errors (ConnectionError/TimeoutError).
    """

    async def _send(**kwargs: Any) -> dict[str, Any]:
        return await send_via_resend(api_key=api_key, **kwargs)

    # `retry_transient` is generic over `Callable[..., Awaitable[T]]` so the
    # exact kw-only signature is erased. Cast back to the Protocol the pipeline
    # expects — the runtime kwargs match.
    return cast(ResendSend, retry_transient(_send))


@app.command()
def send(digest_id: int) -> None:
    """Compose + Resend-send the email for a digest."""

    async def _run() -> int:
        setup_logging()
        s = EmailSettings()
        async with get_session() as session:
            out = await send_digest_email(
                digest_id=digest_id,
                user_repo=UserRepository(session),
                digest_repo=DigestRepository(session),
                email_send_repo=EmailSendRepository(session),
                audit_writer=AuditLogRepository(session).insert,
                resend_send=_resend_send_factory(s.resend.api_key),
                model=s.openai.model,
                sender_name=s.mail.sender_name,
                mail_from=s.mail.mail_from,
                mail_to_default=s.mail.mail_to_default,
            )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command()
def preview(digest_id: int) -> None:
    """Render the digest HTML to stdout (no LLM unless needed; no send)."""

    async def _run() -> int:
        setup_logging()
        s = EmailSettings()
        async with get_session() as session:
            out = await send_digest_email(
                digest_id=digest_id,
                user_repo=UserRepository(session),
                digest_repo=DigestRepository(session),
                email_send_repo=EmailSendRepository(session),
                audit_writer=AuditLogRepository(session).insert,
                resend_send=_resend_send_factory(s.resend.api_key),
                model=s.openai.model,
                sender_name=s.mail.sender_name,
                mail_from=s.mail.mail_from,
                mail_to_default=s.mail.mail_to_default,
                preview_only=True,
            )
        if "html" in out:
            typer.echo(out["html"])
        else:
            typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))
