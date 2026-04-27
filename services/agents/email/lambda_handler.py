"""AWS Lambda entry point for the email agent.

Cold-start: reads SSM params into env vars, configures logging + tracing.
Warm-start: re-uses cached env vars and the Agents SDK client.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, cast

# Pre-init: hydrate env from SSM before any other module reads settings.
from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import get_session, reset_engine  # noqa: E402
from news_db.repositories.audit_log_repo import AuditLogRepository  # noqa: E402
from news_db.repositories.digest_repo import DigestRepository  # noqa: E402
from news_db.repositories.email_send_repo import EmailSendRepository  # noqa: E402
from news_db.repositories.user_repo import UserRepository  # noqa: E402
from news_email import pipeline  # noqa: E402
from news_email.resend_client import send_via_resend  # noqa: E402
from news_email.settings import EmailSettings  # noqa: E402
from news_observability.logging import get_logger, setup_logging  # noqa: E402
from news_observability.retry import retry_transient  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

_log = get_logger("lambda_handler")
setup_logging()
configure_tracing(enable_langfuse=True)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry. ``event = {"digest_id": int}``.

    Returns a structured failure dict on malformed events instead of raising —
    raising would trigger SQS DLQ retries on payloads that will never succeed.
    """
    try:
        digest_id = int(event["digest_id"])
    except (KeyError, TypeError, ValueError) as exc:
        _log.error("malformed event {}: {}", event, exc)
        return {"failed": True, "reason": "malformed_event", "error": str(exc)}
    # Drop the cached SQLAlchemy engine: each invocation runs `asyncio.run(...)`
    # which creates a new event loop, but the pool's asyncpg connections are
    # bound to whichever loop first opened them. On warm-start reuse, the old
    # loop is closed → `RuntimeError: ... attached to a different loop`.
    reset_engine()
    return asyncio.run(_run(digest_id))


async def _run(digest_id: int) -> dict[str, Any]:
    s = EmailSettings()

    async def _send(**kwargs: Any) -> dict[str, Any]:
        return await send_via_resend(api_key=s.resend.api_key, **kwargs)

    # Cast erases the kw-only signature lost through `retry_transient`'s
    # `Callable[..., Awaitable[T]]` generics; runtime kwargs still match.
    resend_send = cast(pipeline.ResendSend, retry_transient(_send))

    async with get_session() as session:
        return await pipeline.send_digest_email(
            digest_id=digest_id,
            user_repo=UserRepository(session),
            digest_repo=DigestRepository(session),
            email_send_repo=EmailSendRepository(session),
            audit_writer=AuditLogRepository(session).insert,
            resend_send=resend_send,
            model=s.openai.model,
            sender_name=s.mail.sender_name,
            mail_from=s.mail.mail_from,
            mail_to_default=s.mail.mail_to_default,
        )
