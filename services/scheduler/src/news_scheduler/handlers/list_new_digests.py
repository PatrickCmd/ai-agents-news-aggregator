"""List handler: today's GENERATED digest IDs for the email stage."""

from __future__ import annotations

from typing import Any

from news_db.engine import get_session
from news_db.repositories.digest_repo import DigestRepository


async def run() -> dict[str, Any]:
    """Return ``{"digest_ids": [...]}`` for the cron's email Map stage."""
    async with get_session() as session:
        repo = DigestRepository(session)
        ids = await repo.list_generated_today()
    return {"digest_ids": ids}
