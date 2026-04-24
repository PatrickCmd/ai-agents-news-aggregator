from datetime import UTC, datetime

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.email_send_repo import EmailSendRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.email_send import EmailSendIn, EmailSendStatus
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
async def test_create_mark_sent_and_failed(session: AsyncSession):
    users = UserRepository(session)
    user = await users.upsert_by_clerk_id(
        UserIn(
            clerk_user_id="e1",
            email="e@b.com",
            name="E",
            email_name="E",
            profile=_profile(),
        )
    )
    now = datetime.now(UTC)
    digest = await DigestRepository(session).create(
        DigestIn(
            user_id=user.id,
            period_start=now,
            period_end=now,
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.GENERATED,
        )
    )

    repo = EmailSendRepository(session)
    es = await repo.create(
        EmailSendIn(
            user_id=user.id,
            digest_id=digest.id,
            to_address="e@b.com",
            subject="subject",
        )
    )
    assert es.status == EmailSendStatus.PENDING

    sent = await repo.mark_sent(es.id, provider_message_id="mid-1")
    assert sent.status == EmailSendStatus.SENT
    assert sent.provider_message_id == "mid-1"

    es2 = await repo.create(
        EmailSendIn(
            user_id=user.id,
            digest_id=digest.id,
            to_address="e@b.com",
            subject="s2",
        )
    )
    failed = await repo.mark_failed(es2.id, error="nope")
    assert failed.status == EmailSendStatus.FAILED
    assert failed.error_message == "nope"
