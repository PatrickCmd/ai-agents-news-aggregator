import pytest
from news_schemas.audit import AgentName, AuditLogIn, DecisionType

from news_observability.audit import AuditLogger


@pytest.mark.asyncio
async def test_audit_logger_calls_writer():
    received: list[AuditLogIn] = []

    async def writer(entry: AuditLogIn) -> None:
        received.append(entry)

    logger = AuditLogger(writer=writer)
    await logger.log_decision(
        agent_name=AgentName.EDITOR,
        user_id=None,
        decision_type=DecisionType.RANK,
        input_text="x" * 5000,
        output_text="y" * 5000,
        metadata={"tokens": 10},
    )
    assert len(received) == 1
    # Size-capped
    assert len(received[0].input_summary) <= 2000
    assert len(received[0].output_summary) <= 2000


@pytest.mark.asyncio
async def test_audit_logger_swallows_writer_errors():
    async def bad_writer(entry: AuditLogIn) -> None:
        raise RuntimeError("writer exploded")

    logger = AuditLogger(writer=bad_writer)
    # Must not raise
    await logger.log_decision(
        agent_name=AgentName.DIGEST,
        user_id=None,
        decision_type=DecisionType.SUMMARY,
        input_text="i",
        output_text="o",
    )
