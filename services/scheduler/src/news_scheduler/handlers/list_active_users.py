"""List handler: active user IDs (onboarding complete) for the editor stage."""

from __future__ import annotations

from typing import Any

from news_db.engine import get_session
from news_db.repositories.user_repo import UserRepository


async def run() -> dict[str, Any]:
    """Return ``{"user_ids": [...]}`` (UUIDs as strings for JSON-safe state-machine input)."""
    async with get_session() as session:
        repo = UserRepository(session)
        ids = await repo.list_active_user_ids()
    return {"user_ids": [str(uid) for uid in ids]}
