"""AuditLogger: fire-and-forget writer for AI decisions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from news_schemas.audit import AgentName, AuditLogIn, DecisionType

from news_observability.limits import (
    MAX_AUDIT_INPUT_CHARS,
    MAX_AUDIT_OUTPUT_CHARS,
    truncate_for_audit,
)
from news_observability.logging import get_logger

_log = get_logger("audit")

AuditWriter = Callable[[AuditLogIn], Awaitable[None]]


class AuditLogger:
    """Thin wrapper that applies size caps and swallows writer errors.

    The writer is injected so observability has no dependency on packages/db.
    """

    def __init__(self, writer: AuditWriter) -> None:
        self._writer = writer

    async def log_decision(
        self,
        *,
        agent_name: AgentName,
        user_id: UUID | None,
        decision_type: DecisionType,
        input_text: str,
        output_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLogIn(
            agent_name=agent_name,
            user_id=user_id,
            decision_type=decision_type,
            input_summary=truncate_for_audit(input_text, MAX_AUDIT_INPUT_CHARS),
            output_summary=truncate_for_audit(output_text, MAX_AUDIT_OUTPUT_CHARS),
            metadata=metadata or {},
        )
        try:
            await self._writer(entry)
        except Exception as e:  # fire-and-forget
            _log.error("audit writer failed: {}", e)
