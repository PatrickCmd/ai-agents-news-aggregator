"""List handler: unsummarised article IDs for the digest stage."""

from __future__ import annotations

from typing import Any

from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository


async def run(*, hours: int, limit: int) -> dict[str, Any]:
    """Return ``{"article_ids": [...]}`` for the cron's digest Map stage.

    Args:
        hours: lookback window in hours.
        limit: cap on number of IDs returned (Step Functions Map cap).
    """
    async with get_session() as session:
        repo = ArticleRepository(session)
        rows = await repo.get_unsummarized(hours=hours, limit=limit)
    return {"article_ids": [r.id for r in rows]}
