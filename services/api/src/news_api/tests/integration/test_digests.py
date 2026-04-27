"""Integration tests for /v1/digests list + detail."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_schemas.digest import DigestIn, DigestStatus

pytestmark = pytest.mark.asyncio


async def _ensure_user_and_digests(
    api_client, auth_header, db_session_factory, *, sub: str, email: str, n: int
):
    """Lazy-create the user via /me, then seed N digests in the DB."""
    h = auth_header(sub=sub, email=email, name=email.split("@")[0])
    me = (await api_client.get("/v1/me", headers=h)).json()
    user_id = me["id"]
    async with db_session_factory() as session:
        repo = DigestRepository(session)
        for i in range(1, n + 1):
            await repo.create(
                DigestIn(
                    user_id=user_id,
                    period_start=datetime(2026, 4, i, tzinfo=UTC),
                    period_end=datetime(2026, 4, i + 1, tzinfo=UTC),
                    intro=f"day-{i}",
                    ranked_articles=[],
                    top_themes=[],
                    article_count=0,
                    status=DigestStatus.GENERATED,
                )
            )
    return h, user_id


async def test_digests_paginates(api_client, auth_header, db_session_factory):
    h, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_dl1", email="dl1@x.com", n=5
    )

    page1 = await api_client.get("/v1/digests?limit=2", headers=h)
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["next_before"] == body1["items"][-1]["id"]
    # Confirm summary projection — no ranked_articles in the response.
    assert "ranked_articles" not in body1["items"][0]

    page2 = await api_client.get(
        f"/v1/digests?limit=2&before={body1['next_before']}",
        headers=h,
    )
    body2 = page2.json()
    assert len(body2["items"]) == 2

    page3 = await api_client.get(
        f"/v1/digests?limit=2&before={body2['next_before']}",
        headers=h,
    )
    body3 = page3.json()
    assert len(body3["items"]) == 1
    assert body3["next_before"] is None


async def test_digests_isolates_users(api_client, auth_header, db_session_factory):
    h_a, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_dlA", email="dla@x.com", n=2
    )
    h_b, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_dlB", email="dlb@x.com", n=3
    )
    a = (await api_client.get("/v1/digests?limit=10", headers=h_a)).json()
    b = (await api_client.get("/v1/digests?limit=10", headers=h_b)).json()
    assert len(a["items"]) == 2
    assert len(b["items"]) == 3


async def test_digest_detail_owner_succeeds(api_client, auth_header, db_session_factory):
    h, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_dd1", email="dd1@x.com", n=1
    )
    listing = (await api_client.get("/v1/digests?limit=1", headers=h)).json()
    digest_id = listing["items"][0]["id"]

    resp = await api_client.get(f"/v1/digests/{digest_id}", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == digest_id
    assert "ranked_articles" in body  # full projection


async def test_digest_detail_other_user_404s(api_client, auth_header, db_session_factory):
    h_a, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_ddA", email="dda@x.com", n=1
    )
    h_b, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_ddB", email="ddb@x.com", n=1
    )
    listing_a = (await api_client.get("/v1/digests?limit=1", headers=h_a)).json()
    a_digest_id = listing_a["items"][0]["id"]

    resp = await api_client.get(f"/v1/digests/{a_digest_id}", headers=h_b)
    assert resp.status_code == 404


async def test_digest_detail_nonexistent_404s(api_client, auth_header, db_session_factory):
    h, _ = await _ensure_user_and_digests(
        api_client, auth_header, db_session_factory, sub="user_ddX", email="ddx@x.com", n=0
    )
    resp = await api_client.get("/v1/digests/999999999", headers=h)
    assert resp.status_code == 404
