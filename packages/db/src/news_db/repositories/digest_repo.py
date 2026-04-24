from __future__ import annotations

from uuid import UUID

from news_schemas.digest import DigestIn, DigestOut, DigestStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.digest import Digest


class DigestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, digest: DigestIn) -> DigestOut:
        row = Digest(
            user_id=digest.user_id,
            period_start=digest.period_start,
            period_end=digest.period_end,
            intro=digest.intro,
            ranked_articles=[r.model_dump(mode="json") for r in digest.ranked_articles],
            top_themes=list(digest.top_themes),
            article_count=digest.article_count,
            status=digest.status.value,
            error_message=digest.error_message,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return DigestOut.model_validate(row, from_attributes=True)

    async def update_status(
        self, digest_id: int, status: DigestStatus, error: str | None = None
    ) -> DigestOut:
        row = await self._session.get(Digest, digest_id)
        if row is None:
            raise ValueError(f"digest not found: {digest_id}")
        row.status = status.value
        row.error_message = error
        await self._session.commit()
        await self._session.refresh(row)
        return DigestOut.model_validate(row, from_attributes=True)

    async def get_recent_for_user(self, user_id: UUID, limit: int) -> list[DigestOut]:
        stmt = (
            select(Digest)
            .where(Digest.user_id == user_id)
            .order_by(Digest.generated_at.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [DigestOut.model_validate(r, from_attributes=True) for r in rows]

    async def get_by_id(self, digest_id: int) -> DigestOut | None:
        row = await self._session.get(Digest, digest_id)
        return DigestOut.model_validate(row, from_attributes=True) if row else None
