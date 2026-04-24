import pytest
from news_schemas.audit import AgentName, AuditLogIn, DecisionType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.audit_log import AuditLog
from news_db.repositories.audit_log_repo import AuditLogRepository


@pytest.mark.asyncio
async def test_insert_round_trip(session: AsyncSession):
    repo = AuditLogRepository(session)
    await repo.insert(
        AuditLogIn(
            agent_name=AgentName.WEB_SEARCH,
            user_id=None,
            decision_type=DecisionType.SEARCH_RESULT,
            input_summary="in",
            output_summary="out",
            metadata={"tokens": 7},
        )
    )
    rows = (await session.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1
    assert rows[0].agent_name == "web_search_agent"
    assert rows[0].meta == {"tokens": 7}
