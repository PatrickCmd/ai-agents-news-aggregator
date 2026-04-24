"""Logging configuration. Loguru for dev; JSON for Lambda/ECS."""

from __future__ import annotations

import os
import sys

from loguru import logger as _logger

_DEFAULT_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


def setup_logging(level: str | None = None, json_mode: bool | None = None) -> None:
    """Idempotent logging setup.

    - json_mode=True emits line-delimited JSON suitable for CloudWatch.
    - level defaults to the LOG_LEVEL env var, then INFO.
    """
    if not level:
        level = os.getenv("LOG_LEVEL", "INFO")
    resolved_level = level.upper()
    if json_mode is None:
        json_mode = os.getenv("LOG_JSON", "false").lower() == "true"

    _logger.remove()
    if json_mode:
        _logger.add(sys.stderr, level=resolved_level, serialize=True)
    else:
        _logger.add(sys.stderr, level=resolved_level, format=_DEFAULT_FORMAT, colorize=True)


def get_logger(name: str):  # type: ignore[no-untyped-def]
    """Return a loguru logger bound to a name."""
    return _logger.bind(name=name)


# Run once on import so `from news_observability.logging import get_logger` just works.
setup_logging()
