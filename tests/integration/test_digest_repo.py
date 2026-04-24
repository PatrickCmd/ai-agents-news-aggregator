from datetime import UTC, datetime

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus, RankedArticle
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
        interests=Interests(primary=[], secondary=[], specific_topics=[]),
        preferences=Preferences(content_type=[], avoid=[]),
        goals=[],
        reading_time=ReadingTime(daily_limit="15", preferred_article_count="5"),
    )


@pytest.mark.asyncio
async def test_create_update_status(session: AsyncSession):
    users = UserRepository(session)
    user = await users.upsert_by_clerk_id(
        UserIn(
            clerk_user_id="d1",
            email="d@b.com",
            name="D",
            email_name="D",
            profile=_profile(),
        )
    )

    digests = DigestRepository(session)
    now = datetime.now(UTC)
    d = await digests.create(
        DigestIn(
            user_id=user.id,
            period_start=now,
            period_end=now,
            intro=None,
            ranked_articles=[
                RankedArticle(
                    article_id=1,
                    score=90,
                    title="t",
                    url="https://u",
                    summary="s",
                    why_ranked="w",
                ),
            ],
            top_themes=[],
            article_count=1,
            status=DigestStatus.PENDING,
        )
    )
    assert d.status == DigestStatus.PENDING
    d2 = await digests.update_status(d.id, DigestStatus.GENERATED)
    assert d2.status == DigestStatus.GENERATED
