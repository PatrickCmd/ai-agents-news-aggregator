from __future__ import annotations

from news_schemas.audit import AuditLogIn
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(self, entry: AuditLogIn) -> None:
        row = AuditLog(
            agent_name=entry.agent_name.value,
            user_id=entry.user_id,
            decision_type=entry.decision_type.value,
            input_summary=entry.input_summary,
            output_summary=entry.output_summary,
            meta=entry.metadata,
        )
        self._session.add(row)
        await self._session.commit()
