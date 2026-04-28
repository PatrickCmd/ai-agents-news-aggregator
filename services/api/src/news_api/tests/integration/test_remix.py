"""Integration tests for POST /v1/remix."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio

_SAMPLE_PROFILE = {
    "background": ["AI engineer"],
    "interests": {"primary": ["LLMs"], "secondary": [], "specific_topics": []},
    "preferences": {"content_type": [], "avoid": []},
    "goals": [],
    "reading_time": {"daily_limit": "20 minutes", "preferred_article_count": "8"},
}


@pytest.fixture
def mock_start_remix(monkeypatch):
    """Replace start_remix with a recording AsyncMock."""
    from news_api.routes import remix as remix_module

    mock = AsyncMock(
        return_value=(
            "arn:aws:states:us-east-1:111:execution:news-remix-user-dev:test-exec-1",
            datetime(2026, 4, 27, 10, 0, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(remix_module, "start_remix", mock)
    return mock


async def test_remix_409_when_profile_incomplete(api_client, auth_header, mock_start_remix):
    h = auth_header(sub="user_rx1", email="rx1@x.com", name="R")
    await api_client.get("/v1/me", headers=h)  # lazy-creates with empty profile

    resp = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 24})
    assert resp.status_code == 409
    body = resp.json()
    # FastAPI wraps non-string `detail` in `{"detail": ...}`.
    error_payload = body.get("error") or body.get("detail", {}).get("error")
    assert error_payload == "profile_incomplete"
    mock_start_remix.assert_not_called()


async def test_remix_202_starts_execution_with_correct_payload(
    api_client, auth_header, mock_start_remix
):
    h = auth_header(sub="user_rx2", email="rx2@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    resp = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 12})
    assert resp.status_code == 202
    body = resp.json()
    assert body["execution_arn"].endswith(":test-exec-1")
    assert (
        body["started_at"] == "2026-04-27T10:00:00Z"
        or body["started_at"] == "2026-04-27T10:00:00+00:00"
    )

    mock_start_remix.assert_called_once()
    call_kwargs = mock_start_remix.call_args.kwargs
    assert call_kwargs["lookback_hours"] == 12
    # user_id is a UUID — not a string. Just confirm it has hex attribute.
    assert hasattr(call_kwargs["user_id"], "hex")


async def test_remix_default_lookback_hours_is_24(api_client, auth_header, mock_start_remix):
    h = auth_header(sub="user_rx3", email="rx3@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    resp = await api_client.post("/v1/remix", headers=h, json={})
    assert resp.status_code == 202
    assert mock_start_remix.call_args.kwargs["lookback_hours"] == 24


async def test_remix_rejects_lookback_out_of_range(api_client, auth_header, mock_start_remix):
    h = auth_header(sub="user_rx4", email="rx4@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    too_small = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 0})
    too_big = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 200})
    assert too_small.status_code == 422
    assert too_big.status_code == 422
    mock_start_remix.assert_not_called()


async def test_remix_503_when_state_machine_arn_missing(
    api_client, auth_header, monkeypatch, mock_start_remix
):
    """Local-dev / misconfigured-deploy path: empty ARN → 503, no SFN call."""
    from news_api.settings import get_api_settings

    monkeypatch.delenv("REMIX_STATE_MACHINE_ARN", raising=False)
    monkeypatch.setenv("REMIX_STATE_MACHINE_ARN", "")
    get_api_settings.cache_clear()

    h = auth_header(sub="user_rx_unconf", email="rxu@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)

    resp = await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 24})
    assert resp.status_code == 503
    body = resp.json()
    error_payload = body.get("error") or body.get("detail", {}).get("error")
    assert error_payload == "remix_unconfigured"
    mock_start_remix.assert_not_called()


async def test_remix_writes_audit_row(
    api_client, auth_header, mock_start_remix, db_session_factory
):
    from news_db.models.audit_log import AuditLog
    from sqlalchemy import select

    h = auth_header(sub="user_rx5", email="rx5@x.com", name="R")
    await api_client.get("/v1/me", headers=h)
    await api_client.put("/v1/me/profile", headers=h, json=_SAMPLE_PROFILE)
    await api_client.post("/v1/remix", headers=h, json={"lookback_hours": 6})

    async with db_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.decision_type == "remix_triggered")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) >= 1
