from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Interests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    specific_topics: list[str] = Field(default_factory=list)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class ReadingTime(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_limit: str
    preferred_article_count: str


class UserProfile(BaseModel):
    """Mirrors config/user_profile.yml. Stored as users.profile JSONB."""

    model_config = ConfigDict(extra="forbid")

    background: list[str] = Field(default_factory=list)
    interests: Interests
    preferences: Preferences
    goals: list[str] = Field(default_factory=list)
    reading_time: ReadingTime

    @classmethod
    def empty(cls) -> UserProfile:
        """Empty / not-yet-onboarded profile.

        Used by the API's lazy-upsert path before the user has visited the
        profile editor. The editor agent filters by `profile_completed_at IS
        NOT NULL`, so empty profiles are inert until the user completes
        onboarding.
        """
        return cls(
            background=[],
            interests=Interests(primary=[], secondary=[], specific_topics=[]),
            preferences=Preferences(content_type=[], avoid=[]),
            goals=[],
            reading_time=ReadingTime(
                daily_limit="30 minutes",
                preferred_article_count="10",
            ),
        )


class UserIn(BaseModel):
    clerk_user_id: str = Field(..., min_length=1)
    email: EmailStr
    name: str = Field(..., min_length=1)
    email_name: str = Field(..., min_length=1)
    profile: UserProfile
    profile_completed_at: datetime | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clerk_user_id: str
    email: EmailStr
    name: str
    email_name: str
    profile: UserProfile
    profile_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
