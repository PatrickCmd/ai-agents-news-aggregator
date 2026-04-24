from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from news_schemas.user_profile import (
    UserIn,
    UserOut,
    UserProfile,
)


def _valid_profile_dict() -> dict:
    return {
        "background": ["SWE 5+ years"],
        "interests": {
            "primary": ["LLMs"],
            "secondary": ["AI safety"],
            "specific_topics": ["RAG"],
        },
        "preferences": {
            "content_type": ["deep-dives"],
            "avoid": ["hype"],
        },
        "goals": ["stay current"],
        "reading_time": {
            "daily_limit": "15-20 minutes",
            "preferred_article_count": "5-10",
        },
    }


def test_user_profile_round_trips():
    p = UserProfile.model_validate(_valid_profile_dict())
    assert p.interests.primary == ["LLMs"]
    assert p.reading_time.daily_limit == "15-20 minutes"


def test_user_profile_rejects_missing_interests():
    bad = _valid_profile_dict()
    del bad["interests"]
    with pytest.raises(ValidationError):
        UserProfile.model_validate(bad)


def test_user_in_requires_clerk_and_email():
    u = UserIn(
        clerk_user_id="dev-seed-user",
        email="a@b.com",
        name="A",
        email_name="A",
        profile=UserProfile.model_validate(_valid_profile_dict()),
    )
    assert u.profile_completed_at is None


def test_user_out_round_trip():
    now = datetime.now(UTC)
    u = UserOut(
        id=uuid4(),
        clerk_user_id="x",
        email="a@b.com",
        name="A",
        email_name="A",
        profile=UserProfile.model_validate(_valid_profile_dict()),
        profile_completed_at=None,
        created_at=now,
        updated_at=now,
    )
    assert u.clerk_user_id == "x"
