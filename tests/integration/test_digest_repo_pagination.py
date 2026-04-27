"""Integration test for DigestRepository.get_for_user — cursor pagination."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.user_profile import UserIn, UserProfile

pytestmark = pytest.mark.asyncio


async def _seed_user(session) -> UUID:
    repo = UserRepository(session)
    user = await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"user_{uuid4().hex[:8]}",
            email=f"u_{uuid4().hex[:8]}@example.com",
            name="Test User",
            email_name="Test",
            profile=UserProfile.empty(),
            profile_completed_at=datetime.now(UTC),
        )
    )
    return user.id


def _digest_in(user_id: UUID, n: int) -> DigestIn:
    return DigestIn(
        user_id=user_id,
        period_start=datetime(2026, 4, n, tzinfo=UTC),
        period_end=datetime(2026, 4, n + 1, tzinfo=UTC),
        intro=f"day-{n}",
        ranked_articles=[],
        top_themes=[],
        article_count=0,
        status=DigestStatus.GENERATED,
    )


async def test_get_for_user_returns_desc_by_id_paged(db_session_factory):
    async with db_session_factory() as session:
        user_id = await _seed_user(session)
        repo = DigestRepository(session)
        ids = [(await repo.create(_digest_in(user_id, n))).id for n in range(1, 6)]

    # Page 1: limit=2, before=None → returns the two most recent.
    async with db_session_factory() as session:
        page1 = await DigestRepository(session).get_for_user(user_id, limit=2, before=None)
    assert [d.id for d in page1] == [ids[4], ids[3]]
    assert "ranked_articles" not in page1[0].model_dump()  # confirm it's the summary

    # Page 2.
    async with db_session_factory() as session:
        page2 = await DigestRepository(session).get_for_user(user_id, limit=2, before=page1[-1].id)
    assert [d.id for d in page2] == [ids[2], ids[1]]

    # Page 3: only 1 row remains.
    async with db_session_factory() as session:
        page3 = await DigestRepository(session).get_for_user(user_id, limit=2, before=page2[-1].id)
    assert [d.id for d in page3] == [ids[0]]


async def test_get_for_user_isolates_users(db_session_factory):
    async with db_session_factory() as session:
        a = await _seed_user(session)
        b = await _seed_user(session)
        repo = DigestRepository(session)
        await repo.create(_digest_in(a, 1))
        await repo.create(_digest_in(b, 2))

    async with db_session_factory() as session:
        a_digests = await DigestRepository(session).get_for_user(a, limit=10, before=None)
        b_digests = await DigestRepository(session).get_for_user(b, limit=10, before=None)
    assert {d.user_id for d in a_digests} == {a}
    assert {d.user_id for d in b_digests} == {b}
