"""Promote config/user_profile.yml → users row.

Uses placeholder clerk_user_id='dev-seed-user' until Clerk integration
(sub-project #4). Idempotent: re-running updates the existing row.
"""

from __future__ import annotations

import asyncio
import os
import sys

from news_config.loader import load_user_profile_yaml
from news_db.engine import get_session
from news_db.repositories.user_repo import UserRepository
from news_observability.logging import get_logger
from news_schemas.user_profile import UserIn

log = get_logger("seed_user")


async def main() -> int:
    profile, identity = load_user_profile_yaml()
    email = os.getenv("SEED_USER_EMAIL", "seed@example.com")

    user_in = UserIn(
        clerk_user_id="dev-seed-user",
        email=email,
        name=identity["name"],
        email_name=identity["email_name"],
        profile=profile,
    )

    async with get_session() as session:
        repo = UserRepository(session)
        user = await repo.upsert_by_clerk_id(user_in)

    log.info("seeded user id={} email={}", user.id, user.email)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
