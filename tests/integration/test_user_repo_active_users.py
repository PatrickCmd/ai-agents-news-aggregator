from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from news_db.repositories.user_repo import UserRepository
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
async def test_list_active_user_ids_excludes_unfinished_profiles(
    session: AsyncSession,
) -> None:
    repo = UserRepository(session)

    # Active user — profile_completed_at is set.
    active = await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email=f"{uuid4()}@example.com",
            name="Active",
            email_name="Active",
            profile=_profile(),
            profile_completed_at=datetime.now(UTC),
        )
    )

    # Inactive user — onboarding incomplete.
    await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email=f"{uuid4()}@example.com",
            name="Pending",
            email_name="Pending",
            profile=_profile(),
            profile_completed_at=None,
        )
    )

    ids = await repo.list_active_user_ids()
    assert active.id in ids
    assert len(ids) == 1


@pytest.mark.asyncio
async def test_list_active_user_ids_returns_empty_when_none(session: AsyncSession) -> None:
    repo = UserRepository(session)
    ids = await repo.list_active_user_ids()
    assert ids == []
