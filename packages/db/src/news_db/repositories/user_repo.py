from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from news_schemas.user_profile import UserIn, UserOut, UserProfile
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_by_clerk_id(self, user: UserIn) -> UserOut:
        payload = {
            "clerk_user_id": user.clerk_user_id,
            "email": user.email,
            "name": user.name,
            "email_name": user.email_name,
            "profile": user.profile.model_dump(mode="json"),
            "profile_completed_at": user.profile_completed_at,
        }
        stmt = (
            pg_insert(User)
            .values(payload)
            .on_conflict_do_update(
                index_elements=[User.clerk_user_id],
                set_={
                    "email": payload["email"],
                    "name": payload["name"],
                    "email_name": payload["email_name"],
                    "profile": payload["profile"],
                    "profile_completed_at": payload["profile_completed_at"],
                },
            )
            .returning(User)
        )
        row = (await self._session.execute(stmt)).scalar_one()
        await self._session.commit()
        return UserOut.model_validate(row, from_attributes=True)

    async def get_by_clerk_id(self, clerk_user_id: str) -> UserOut | None:
        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return UserOut.model_validate(row, from_attributes=True) if row else None

    async def get_by_id(self, user_id: UUID) -> UserOut | None:
        row = await self._session.get(User, user_id)
        return UserOut.model_validate(row, from_attributes=True) if row else None

    async def mark_profile_complete(self, user_id: UUID) -> UserOut:
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user not found: {user_id}")
        row.profile_completed_at = datetime.now(UTC)
        await self._session.commit()
        await self._session.refresh(row)
        return UserOut.model_validate(row, from_attributes=True)

    async def update_profile(self, user_id: UUID, profile: UserProfile) -> UserOut:
        row = await self._session.get(User, user_id)
        if row is None:
            raise ValueError(f"user not found: {user_id}")
        row.profile = profile.model_dump(mode="json")
        await self._session.commit()
        await self._session.refresh(row)
        return UserOut.model_validate(row, from_attributes=True)
