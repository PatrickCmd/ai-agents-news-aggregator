"""Destructive: drop + recreate public schema, re-run migrations, re-seed.

Guard: refuses unless the DB URL's database name contains 'dev' or 'local'.
Usage: uv run python scripts/reset_db.py --confirm
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from urllib.parse import urlparse

from news_db.engine import get_engine, reset_engine
from news_observability.logging import get_logger
from sqlalchemy import text

log = get_logger("reset_db")


def _assert_dev_db(url: str) -> None:
    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/")
    if "dev" not in db_name.lower() and "local" not in db_name.lower():
        raise RuntimeError(
            f"refusing to reset DB: name '{db_name}' does not contain 'dev' or 'local'"
        )


async def _drop_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("drop schema if exists public cascade"))
        await conn.execute(text("create schema public"))
    reset_engine()


def _run_migrations() -> None:
    subprocess.run(
        ["uv", "run", "alembic", "-c", "packages/db/alembic.ini", "upgrade", "head"],
        check=True,
        env=os.environ.copy(),
    )


def _run_seed() -> None:
    subprocess.run(["uv", "run", "python", "scripts/seed_user.py"], check=True)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", required=True)
    ap.parse_args()

    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("SUPABASE_POOLER_URL")
    if not url:
        log.error("SUPABASE_DB_URL or SUPABASE_POOLER_URL required")
        return 2
    _assert_dev_db(url)

    log.warning("dropping public schema on {}", urlparse(url).hostname)
    await _drop_schema()
    log.info("running migrations")
    _run_migrations()
    log.info("seeding dev user")
    _run_seed()
    log.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
