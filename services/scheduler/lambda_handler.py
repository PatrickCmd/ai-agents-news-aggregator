"""AWS Lambda entry point for the scheduler.

Dispatches by ``event["op"]`` to one of the three list handlers.
Cold-start: hydrates env from SSM, configures logging.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# Pre-init: hydrate env from SSM before any other module reads settings.
from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from news_db.engine import reset_engine  # noqa: E402
from news_observability.logging import get_logger, setup_logging  # noqa: E402
from news_scheduler.handlers import (  # noqa: E402
    list_active_users,
    list_new_digests,
    list_unsummarised,
)

_log = get_logger("lambda_handler")
setup_logging()


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry. Dispatches by ``event["op"]``.

    Supported ops:
        ``list_unsummarised`` (kwargs: ``hours``, ``limit``)
        ``list_active_users``
        ``list_new_digests``

    Returns ``{"failed": True, "reason": ..., ...}`` on bad input — never raises.
    """
    # Drop the cached SQLAlchemy engine: each invocation runs `asyncio.run(...)`
    # which creates a new event loop, but the pool's asyncpg connections are
    # bound to whichever loop first opened them. On warm-start reuse, the old
    # loop is closed → `RuntimeError: ... attached to a different loop`.
    reset_engine()
    op = event.get("op")
    if not op:
        _log.error("malformed event {}: missing op", event)
        return {"failed": True, "reason": "malformed_event", "event": event}

    if op == "list_unsummarised":
        hours = int(event.get("hours", 24))
        limit = int(event.get("limit", 200))
        return asyncio.run(list_unsummarised.run(hours=hours, limit=limit))

    if op == "list_active_users":
        return asyncio.run(list_active_users.run())

    if op == "list_new_digests":
        return asyncio.run(list_new_digests.run())

    _log.error("unknown op {}", op)
    return {"failed": True, "reason": "unknown_op", "op": op}
