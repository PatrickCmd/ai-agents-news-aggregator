from datetime import datetime, timedelta, timezone

import pytest
from news_schemas.article import ArticleIn, SourceType
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.repositories.article_repo import ArticleRepository


@pytest.mark.asyncio
async def test_upsert_and_get_recent(session: AsyncSession):
    repo = ArticleRepository(session)
    now = datetime.now(timezone.utc)
    items = [
        ArticleIn(
            source_type=SourceType.RSS,
            source_name="openai_news",
            external_id=f"a-{i}",
            title=f"t{i}",
            url="https://example.com/a",
            published_at=now - timedelta(hours=i),
        )
        for i in range(3)
    ]
    inserted = await repo.upsert_many(items)
    assert inserted == 3

    inserted_again = await repo.upsert_many(items)
    assert inserted_again == 0

    recent = await repo.get_recent(hours=24)
    assert len(recent) == 3


@pytest.mark.asyncio
async def test_get_recent_filters_by_source_type(session: AsyncSession):
    repo = ArticleRepository(session)
    now = datetime.now(timezone.utc)
    await repo.upsert_many(
        [
            ArticleIn(
                source_type=SourceType.RSS,
                source_name="x",
                external_id="r1",
                title="r",
                url="https://u",
                published_at=now,
            ),
            ArticleIn(
                source_type=SourceType.YOUTUBE,
                source_name="x",
                external_id="y1",
                title="y",
                url="https://u",
                published_at=now,
            ),
        ]
    )
    only_yt = await repo.get_recent(hours=24, source_types=[SourceType.YOUTUBE])
    assert len(only_yt) == 1
    assert only_yt[0].source_type == SourceType.YOUTUBE
