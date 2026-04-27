"""AWS Lambda entry point for the API service.

Cold-start: hydrates env from SSM, configures logging + tracing, builds
the FastAPI app and the Mangum adapter once.

Per-invocation: calls reset_engine() before the ASGI dispatch — same
warm-start asyncio-loop fix as #2/#3 — then delegates to Mangum.
"""

from __future__ import annotations

import os
from typing import Any

from news_config.lambda_settings import load_settings_from_ssm

load_settings_from_ssm(prefix=os.environ.get("SSM_PARAM_PREFIX", "/news-aggregator/dev"))

from mangum import Mangum  # noqa: E402
from news_api.app import create_app  # noqa: E402
from news_db.engine import reset_engine  # noqa: E402
from news_observability.logging import get_logger, setup_logging  # noqa: E402
from news_observability.tracing import configure_tracing  # noqa: E402

_log = get_logger("lambda_handler")
setup_logging()
configure_tracing(enable_langfuse=True)

_app = create_app()
_asgi_handler = Mangum(_app, lifespan="off")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    # Drop the cached SQLAlchemy engine: each invocation runs through
    # asyncio under the hood, but the pool's asyncpg connections are bound
    # to whichever loop first opened them. On warm-start reuse, the old
    # loop is closed → "RuntimeError: ... attached to a different loop".
    reset_engine()
    return _asgi_handler(event, context)
