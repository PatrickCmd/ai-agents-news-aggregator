"""Async SQLAlchemy engine + session factory for Supabase Postgres.

Runtime uses the pgbouncer pooler URL with statement_cache_size=0 (transaction
mode pgbouncer does not tolerate prepared statements). Migrations use the
direct URL (see alembic/env.py).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from news_config.settings import DatabaseSettings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine(url: str | None = None) -> AsyncEngine:
    """Return a singleton async engine bound to the pooler URL."""
    global _engine, _sessionmaker
    if _engine is None:
        settings = DatabaseSettings()
        resolved = url or settings.supabase_pooler_url or settings.supabase_db_url
        if not resolved:
            raise RuntimeError("No DB URL: set SUPABASE_POOLER_URL or SUPABASE_DB_URL")
        _engine = create_async_engine(
            resolved,
            echo=False,
            pool_pre_ping=True,
            connect_args={"statement_cache_size": 0},
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Drop the singleton. Useful in tests."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession. Commits on success, rolls back on error."""
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
