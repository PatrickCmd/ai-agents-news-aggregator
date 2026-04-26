from __future__ import annotations

from datetime import UTC, datetime, timedelta

from news_schemas.article import ArticleIn, ArticleOut, SourceType
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.article import Article


class ArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, items: list[ArticleIn]) -> int:
        if not items:
            return 0
        payload = [
            {
                "source_type": i.source_type.value,
                "source_name": i.source_name,
                "external_id": i.external_id,
                "title": i.title,
                "url": str(i.url),
                "author": i.author,
                "published_at": i.published_at,
                "content_text": i.content_text,
                "tags": i.tags,
                "raw": i.raw,
            }
            for i in items
        ]
        stmt = (
            pg_insert(Article)
            .values(payload)
            .on_conflict_do_nothing(constraint="articles_source_external_uk")
            .returning(Article.id)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return len(result.scalars().all())

    async def get_recent(
        self, hours: int, source_types: list[SourceType] | None = None
    ) -> list[ArticleOut]:
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        stmt = select(Article).where(Article.published_at >= cutoff)
        if source_types:
            stmt = stmt.where(Article.source_type.in_([s.value for s in source_types]))
        stmt = stmt.order_by(Article.published_at.desc())
        rows = (await self._session.execute(stmt)).scalars().all()
        return [ArticleOut.model_validate(r, from_attributes=True) for r in rows]

    async def get_by_id(self, article_id: int) -> ArticleOut | None:
        row = await self._session.get(Article, article_id)
        return ArticleOut.model_validate(row, from_attributes=True) if row else None

    async def get_existing_external_ids(
        self, source_type: SourceType, external_ids: list[str]
    ) -> set[str]:
        """Return the subset of *external_ids* already stored for *source_type*.

        Used by pipelines to skip expensive per-item work (transcript fetch,
        agent crawl) for articles already in the DB.
        """
        if not external_ids:
            return set()
        stmt = select(Article.external_id).where(
            Article.source_type == source_type.value,
            Article.external_id.in_(external_ids),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return set(rows)

    async def update_summary(self, article_id: int, summary: str) -> None:
        row = await self._session.get(Article, article_id)
        if row is None:
            raise ValueError(f"article not found: {article_id}")
        row.summary = summary
        await self._session.commit()
