from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserIn,
    UserProfile,
)
from sqlalchemy.ext.asyncio import AsyncSession


def _profile() -> UserProfile:
    return UserProfile(
        background=[],
        interests=Interests(),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


@pytest.mark.asyncio
async def test_list_generated_today_filters_status_and_date(
    session: AsyncSession,
) -> None:
    user = await UserRepository(session).upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email=f"{uuid4()}@example.com",
            name="t",
            email_name="t",
            profile=_profile(),
        )
    )

    digests = DigestRepository(session)

    now = datetime.now(UTC)
    period = (now - timedelta(hours=24), now)

    # GENERATED today — included.
    fresh = await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=period[0],
            period_end=period[1],
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.GENERATED,
        )
    )
    # FAILED today — excluded by status filter.
    await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=period[0],
            period_end=period[1],
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.FAILED,
            error_message="no candidates",
        )
    )
    # EMAILED today — excluded (already sent).
    await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=period[0],
            period_end=period[1],
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.EMAILED,
        )
    )

    ids = await digests.list_generated_today()
    assert ids == [fresh.id]


@pytest.mark.asyncio
async def test_list_generated_today_returns_empty_when_none(session: AsyncSession) -> None:
    digests = DigestRepository(session)
    ids = await digests.list_generated_today()
    assert ids == []
