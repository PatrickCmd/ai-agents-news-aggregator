"""Root pytest config — DB testcontainer fixtures shared across every tree.

Pytest only walks UP from a test file looking for `conftest.py`. The
testcontainers-postgres fixtures (`pg_container`, `session`,
`db_session_factory`) need to be visible from BOTH `tests/integration/`
and `services/<svc>/.../tests/integration/`. The cleanest way is to
host them at the repo root so every test path's walk-up reaches them.

(We tried registering `tests/integration/conftest.py` as a plugin via
`pytest_plugins`, but pytest also discovers it via normal walk-up for
top-level integration tests, which triggers a double-registration error
inside pluggy. Hosting fixtures at the root sidesteps that entirely.)

Isolation strategy: session-scoped container, but per-test engine —
avoids the pytest-asyncio "event loop is closed" error you get when a
session-scoped async engine's connection pool outlives the loop that
created it. Per-test DB state is wiped via TRUNCATE ... CASCADE at
teardown.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator, Callable, Iterator

import pytest
import pytest_asyncio
from news_db import engine as engine_module
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine") as c:
        url = c.get_connection_url()
        async_url = url.replace("postgresql+psycopg2", "postgresql+asyncpg").replace(
            "postgresql+psycopg", "postgresql+asyncpg"
        )
        if not async_url.startswith("postgresql+asyncpg://"):
            async_url = "postgresql+asyncpg://" + async_url.split("://", 1)[1]

        os.environ["SUPABASE_POOLER_URL"] = async_url
        os.environ["SUPABASE_DB_URL"] = async_url

        subprocess.run(
            ["uv", "run", "alembic", "-c", "packages/db/alembic.ini", "upgrade", "head"],
            check=True,
            env=os.environ.copy(),
        )
        yield c


@pytest_asyncio.fixture
async def session(pg_container: PostgresContainer) -> AsyncIterator[AsyncSession]:
    engine_module.reset_engine()
    engine = create_async_engine(
        os.environ["SUPABASE_POOLER_URL"],
        connect_args={"statement_cache_size": 0},
    )
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        yield s
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "truncate table audit_logs, email_sends, digests, articles, scraper_runs, users "
                "restart identity cascade"
            )
        )
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(
    pg_container: PostgresContainer,
) -> AsyncIterator[Callable[[], AsyncSession]]:
    """Factory that yields fresh sessions on demand.

    Used by tests that need multiple short-lived sessions in one test
    (seed → API call → verify side-effect). Truncates all tables at
    teardown, like the per-test `session` fixture.
    """
    engine = create_async_engine(
        os.environ["SUPABASE_POOLER_URL"],
        connect_args={"statement_cache_size": 0},
    )
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "truncate table audit_logs, email_sends, digests, articles, scraper_runs, users "
                "restart identity cascade"
            )
        )
    await engine.dispose()
