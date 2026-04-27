import pytest

pytestmark = pytest.mark.asyncio

_SAMPLE_PROFILE = {
    "background": ["AI engineer"],
    "interests": {
        "primary": ["LLMs", "agents"],
        "secondary": ["devops"],
        "specific_topics": ["MCP servers"],
    },
    "preferences": {
        "content_type": ["technical deep dives"],
        "avoid": ["press releases"],
    },
    "goals": ["stay current on agent infra"],
    "reading_time": {
        "daily_limit": "20 minutes",
        "preferred_article_count": "8",
    },
}


async def test_put_profile_first_completion_sets_timestamp(api_client, auth_header):
    h = auth_header(sub="user_pp1", email="pp1@x.com", name="Patty")
    # Lazy-create the user.
    await api_client.get("/v1/me", headers=h)

    resp = await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_completed_at"] is not None
    assert body["profile"]["interests"]["primary"] == ["LLMs", "agents"]


async def test_put_profile_second_call_does_not_re_set_completed_at(api_client, auth_header):
    h = auth_header(sub="user_pp2", email="pp2@x.com", name="Patty")
    await api_client.get("/v1/me", headers=h)

    first = await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)
    completed_at_first = first.json()["profile_completed_at"]
    assert completed_at_first is not None

    second_profile = {**_SAMPLE_PROFILE, "background": ["new bio"]}
    second = await api_client.put("/v1/me/profile", headers=h, json=second_profile)
    body = second.json()
    assert body["profile_completed_at"] == completed_at_first  # unchanged
    assert body["profile"]["background"] == ["new bio"]


async def test_put_profile_rejects_invalid_body(api_client, auth_header):
    h = auth_header(sub="user_pp3", email="pp3@x.com", name="Patty")
    await api_client.get("/v1/me", headers=h)

    bad_body = {"interests": {}}  # missing required nested fields
    resp = await api_client.put("/v1/me/profile", headers=h, json=bad_body)
    assert resp.status_code == 422


async def test_put_profile_writes_audit_row(api_client, auth_header, db_session_factory):
    from news_db.models.audit_log import AuditLog
    from sqlalchemy import select

    h = auth_header(sub="user_pp4", email="pp4@x.com", name="Patty")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    async with db_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.decision_type == "profile_update")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) >= 1
