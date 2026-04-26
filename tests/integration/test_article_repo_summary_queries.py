from __future__ import annotations

from datetime import UTC, datetime

import pytest
from news_db.repositories.article_repo import ArticleRepository
from news_schemas.article import ArticleIn, SourceType
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed(session: AsyncSession) -> ArticleRepository:
    repo = ArticleRepository(session)
    now = datetime.now(UTC)
    await repo.upsert_many(
        [
            ArticleIn(
                source_type=SourceType.RSS,
                source_name="t",
                external_id=f"ext-{i}",
                title=f"t{i}",
                url=f"https://example.com/{i}",
                content_text=f"content {i}",
                published_at=now,
            )
            for i in range(3)
        ]
    )
    return repo


@pytest.mark.asyncio
async def test_get_unsummarized_returns_only_null_summary(session: AsyncSession) -> None:
    repo = await _seed(session)
    rows = await repo.get_recent(hours=1)
    await repo.update_summary(rows[0].id, "summary " * 10)

    pending = await repo.get_unsummarized(hours=1, limit=10)
    pending_ids = {r.id for r in pending}
    assert rows[0].id not in pending_ids
    assert {rows[1].id, rows[2].id} <= pending_ids


@pytest.mark.asyncio
async def test_get_recent_with_summaries_filters_null(session: AsyncSession) -> None:
    repo = await _seed(session)
    rows = await repo.get_recent(hours=1)
    await repo.update_summary(rows[0].id, "summary " * 10)
    await repo.update_summary(rows[1].id, "another summary " * 5)

    summarized = await repo.get_recent_with_summaries(hours=1, limit=10)
    summarized_ids = {r.id for r in summarized}
    assert rows[0].id in summarized_ids
    assert rows[1].id in summarized_ids
    assert rows[2].id not in summarized_ids


@pytest.mark.asyncio
async def test_get_recent_with_summaries_respects_limit(session: AsyncSession) -> None:
    repo = await _seed(session)
    rows = await repo.get_recent(hours=1)
    for r in rows:
        await repo.update_summary(r.id, "x" * 60)
    summarized = await repo.get_recent_with_summaries(hours=1, limit=2)
    assert len(summarized) == 2
