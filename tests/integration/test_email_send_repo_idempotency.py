from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.email_send_repo import EmailSendRepository
from news_db.repositories.user_repo import UserRepository
from news_schemas.digest import DigestIn, DigestStatus
from news_schemas.email_send import EmailSendIn
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
        background=["dev"],
        interests=Interests(primary=["AI"]),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


@pytest.mark.asyncio
async def test_get_sent_for_digest_returns_none_when_missing(
    session: AsyncSession,
) -> None:
    repo = EmailSendRepository(session)
    assert await repo.get_sent_for_digest(999_999) is None


@pytest.mark.asyncio
async def test_get_sent_for_digest_returns_sent_row(session: AsyncSession) -> None:
    user = await UserRepository(session).upsert_by_clerk_id(
        UserIn(
            clerk_user_id=f"clerk-{uuid4()}",
            email="t@example.com",
            name="T",
            email_name="T",
            profile=_profile(),
        )
    )
    digest = await DigestRepository(session).create(
        DigestIn(
            user_id=user.id,
            period_start=datetime.now(UTC) - timedelta(hours=24),
            period_end=datetime.now(UTC),
            ranked_articles=[],
            article_count=0,
            status=DigestStatus.GENERATED,
        )
    )

    email_repo = EmailSendRepository(session)
    pending = await email_repo.create(
        EmailSendIn(
            user_id=user.id,
            digest_id=digest.id,
            to_address="t@example.com",
            subject="hi",
        )
    )
    # Pending should not count as "sent"
    assert await email_repo.get_sent_for_digest(digest.id) is None
    await email_repo.mark_sent(pending.id, provider_message_id="msg-1")
    found = await email_repo.get_sent_for_digest(digest.id)
    assert found is not None
    assert found.provider_message_id == "msg-1"
