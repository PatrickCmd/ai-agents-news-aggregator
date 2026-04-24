import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_tables_exist(session: AsyncSession):
    result = await session.execute(
        text(
            "select table_name from information_schema.tables "
            "where table_schema='public' order by table_name"
        )
    )
    tables = {row[0] for row in result.all()}
    assert {"articles", "users", "digests", "email_sends", "audit_logs"}.issubset(tables)


@pytest.mark.asyncio
async def test_articles_check_constraint_rejects_bad_source_type(session: AsyncSession):
    with pytest.raises(Exception):
        await session.execute(
            text(
                "insert into articles (source_type, source_name, external_id, title, url) "
                "values ('bogus','x','e','t','http://u')"
            )
        )
        await session.commit()
