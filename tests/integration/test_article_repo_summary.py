from __future__ import annotations

from datetime import UTC, datetime

import pytest
from news_db.repositories.article_repo import ArticleRepository
from news_schemas.article import ArticleIn, SourceType
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_update_summary_persists(session: AsyncSession) -> None:
    repo = ArticleRepository(session)
    await repo.upsert_many(
        [
            ArticleIn(
                source_type=SourceType.RSS,
                source_name="t",
                external_id="ext-1",
                title="t",
                url="https://example.com/1",
                published_at=datetime.now(UTC),
            )
        ]
    )
    fetched = await repo.get_recent(hours=1)
    assert fetched and fetched[0].summary is None

    await repo.update_summary(fetched[0].id, "a useful summary " * 5)
    again = await repo.get_by_id(fetched[0].id)
    assert again is not None
    assert again.summary is not None
    assert "useful summary" in again.summary
