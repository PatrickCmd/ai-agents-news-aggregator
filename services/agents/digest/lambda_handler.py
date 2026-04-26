"""AWS Lambda entry point for the digest agent.

Cold-start: reads SSM params into env vars, configures logging + tracing.
Warm-start: re-uses cached env vars and the Agents SDK client.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# Pre-init: hydrate env from SSM before any other module reads settings.
from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import get_session  # noqa: E402
from news_db.repositories.article_repo import ArticleRepository  # noqa: E402
from news_db.repositories.audit_log_repo import AuditLogRepository  # noqa: E402
from news_digest import pipeline  # noqa: E402
from news_digest.settings import DigestSettings  # noqa: E402
from news_observability.logging import get_logger, setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

_log = get_logger("lambda_handler")
setup_logging()
configure_tracing(enable_langfuse=True)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry. ``event = {"article_id": int}``.

    Returns a structured failure dict on malformed events instead of raising —
    raising would trigger SQS DLQ retries on payloads that will never succeed.
    """
    try:
        article_id = int(event["article_id"])
    except (KeyError, TypeError, ValueError) as exc:
        _log.error("malformed event {}: {}", event, exc)
        return {"failed": True, "reason": "malformed_event", "error": str(exc)}
    return asyncio.run(_run(article_id))


async def _run(article_id: int) -> dict[str, Any]:
    settings = DigestSettings()
    async with get_session() as session:
        article_repo = ArticleRepository(session)
        audit_repo = AuditLogRepository(session)
        return await pipeline.summarize_article(
            article_id=article_id,
            article_repo=article_repo,
            audit_writer=audit_repo.insert,
            model=settings.openai.model,
            max_content_chars=settings.max_content_chars,
        )
