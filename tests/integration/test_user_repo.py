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
        background=["SWE"],
        interests=Interests(primary=["LLMs"], secondary=[], specific_topics=[]),
        preferences=Preferences(content_type=["deep-dives"], avoid=[]),
        goals=["learn"],
        reading_time=ReadingTime(daily_limit="15 min", preferred_article_count="5-10"),
    )


@pytest.mark.asyncio
async def test_upsert_by_clerk_id_creates_then_updates(session: AsyncSession):
    repo = UserRepository(session)
    u1 = await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id="c1",
            email="a@b.com",
            name="A",
            email_name="A",
            profile=_profile(),
        )
    )
    assert u1.clerk_user_id == "c1"
    assert u1.profile_completed_at is None

    u2 = await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id="c1",
            email="a@b.com",
            name="Updated",
            email_name="A",
            profile=_profile(),
        )
    )
    assert u2.id == u1.id
    assert u2.name == "Updated"


@pytest.mark.asyncio
async def test_mark_profile_complete(session: AsyncSession):
    repo = UserRepository(session)
    u = await repo.upsert_by_clerk_id(
        UserIn(
            clerk_user_id="c2",
            email="b@b.com",
            name="B",
            email_name="B",
            profile=_profile(),
        )
    )
    assert u.profile_completed_at is None
    u2 = await repo.mark_profile_complete(u.id)
    assert u2.profile_completed_at is not None
