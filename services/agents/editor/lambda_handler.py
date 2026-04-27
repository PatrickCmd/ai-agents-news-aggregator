"""AWS Lambda entry point for the editor agent.

Cold-start: reads SSM params into env vars, configures logging + tracing.
Warm-start: re-uses cached env vars and the Agents SDK client.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import UUID

# Pre-init: hydrate env from SSM before any other module reads settings.
from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import get_session, reset_engine  # noqa: E402
from news_db.repositories.article_repo import ArticleRepository  # noqa: E402
from news_db.repositories.audit_log_repo import AuditLogRepository  # noqa: E402
from news_db.repositories.digest_repo import DigestRepository  # noqa: E402
from news_db.repositories.user_repo import UserRepository  # noqa: E402
from news_editor import pipeline  # noqa: E402
from news_editor.settings import EditorSettings  # noqa: E402
from news_observability.logging import get_logger, setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

_log = get_logger("lambda_handler")
setup_logging()
configure_tracing(enable_langfuse=True)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry. ``event = {"user_id": "<uuid>", "lookback_hours": 24}``.

    Returns a structured failure dict on malformed events instead of raising —
    raising would trigger SQS DLQ retries on payloads that will never succeed.
    """
    try:
        user_id = UUID(event["user_id"])
        lookback_hours = int(event.get("lookback_hours", 24))
    except (KeyError, TypeError, ValueError) as exc:
        _log.error("malformed event {}: {}", event, exc)
        return {"failed": True, "reason": "malformed_event", "error": str(exc)}
    # Drop the cached SQLAlchemy engine: each invocation runs `asyncio.run(...)`
    # which creates a new event loop, but the pool's asyncpg connections are
    # bound to whichever loop first opened them. On warm-start reuse, the old
    # loop is closed → `RuntimeError: ... attached to a different loop`.
    reset_engine()
    return asyncio.run(_run(user_id, lookback_hours))


async def _run(user_id: UUID, lookback_hours: int) -> dict[str, Any]:
    s = EditorSettings()
    async with get_session() as session:
        return await pipeline.rank_for_user(
            user_id=user_id,
            article_repo=ArticleRepository(session),
            user_repo=UserRepository(session),
            digest_repo=DigestRepository(session),
            audit_writer=AuditLogRepository(session).insert,
            model=s.openai.model,
            lookback_hours=lookback_hours,
            limit=s.candidate_limit,
            top_n=s.top_n,
        )
