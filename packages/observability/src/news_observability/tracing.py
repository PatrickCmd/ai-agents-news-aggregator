"""Trace configuration for OpenAI Agents SDK + Langfuse.

Idempotent: safe to call at every Lambda cold-start.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from news_observability.logging import get_logger

_log = get_logger("tracing")

_configured: bool = False


@dataclass(frozen=True)
class TracingState:
    langfuse_enabled: bool


def _langfuse_keys_present() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY")) and bool(os.getenv("LANGFUSE_SECRET_KEY"))


def configure_tracing(enable_langfuse: bool = True) -> TracingState:
    """Configure OpenAI Agents SDK traces + optional Langfuse processor.

    Called once at service/Lambda init. Safe to re-invoke.
    """
    global _configured

    langfuse_enabled = False
    if enable_langfuse and _langfuse_keys_present():
        try:
            from langfuse import Langfuse  # noqa: F401

            # Registering an OpenAI-Agents-SDK trace processor is done here.
            # Full wiring lives in sub-project #2; Foundation only verifies setup.
            langfuse_enabled = True
        except ImportError:  # pragma: no cover
            _log.warning("langfuse not installed; tracing disabled")
            langfuse_enabled = False
    else:
        if enable_langfuse:
            _log.warning("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set — langfuse disabled")

    if not _configured:
        _log.info("tracing configured (langfuse={})", langfuse_enabled)
        _configured = True
    return TracingState(langfuse_enabled=langfuse_enabled)
