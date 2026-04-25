from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_scraper_runs_table_exists(session: AsyncSession) -> None:
    row = (
        await session.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_name='scraper_runs' order by column_name"
            )
        )
    ).all()
    names = {r[0] for r in row}
    assert {
        "id",
        "trigger",
        "status",
        "started_at",
        "completed_at",
        "lookback_hours",
        "pipelines_requested",
        "stats",
        "error_message",
    } <= names


@pytest.mark.asyncio
async def test_scraper_runs_status_check_enforced(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await session.execute(
            text(
                "insert into scraper_runs (id, trigger, status, lookback_hours, "
                "pipelines_requested) values (:id, :t, :s, :lb, :p)"
            ),
            {
                "id": str(uuid4()),
                "t": "api",
                "s": "bogus",
                "lb": 24,
                "p": ["youtube"],
            },
        )
        await session.commit()
