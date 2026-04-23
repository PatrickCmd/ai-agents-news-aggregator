from uuid import uuid4

from news_schemas.audit import AgentName, AuditLogIn, DecisionType


def test_audit_log_in_minimal():
    a = AuditLogIn(
        agent_name=AgentName.EDITOR,
        user_id=uuid4(),
        decision_type=DecisionType.RANK,
        input_summary="in",
        output_summary="out",
        metadata={"tokens": 42},
    )
    assert a.agent_name == AgentName.EDITOR


def test_audit_log_in_allows_null_user():
    a = AuditLogIn(
        agent_name=AgentName.WEB_SEARCH,
        user_id=None,
        decision_type=DecisionType.SEARCH_RESULT,
        input_summary="",
        output_summary="",
        metadata={},
    )
    assert a.user_id is None
