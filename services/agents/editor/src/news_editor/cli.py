"""Local Typer CLI for the editor agent."""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import typer
from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.digest_repo import DigestRepository
from news_db.repositories.user_repo import UserRepository
from news_observability.logging import setup_logging

from news_editor.pipeline import rank_for_user
from news_editor.settings import EditorSettings

app = typer.Typer(no_args_is_help=True, help="Editor agent CLI")


@app.callback()
def _root() -> None:
    """Editor agent CLI.

    Forces Typer to keep subcommand routing even when only one command is
    registered (otherwise `python -m news_editor rank <uuid>` would parse
    `rank` as the USER_ID positional).
    """


@app.command()
def rank(user_id: UUID, hours: int = 24) -> None:
    """Rank recent articles for a user; writes a `digests` row."""

    async def _run() -> int:
        setup_logging()
        s = EditorSettings()
        async with get_session() as session:
            out = await rank_for_user(
                user_id=user_id,
                article_repo=ArticleRepository(session),
                user_repo=UserRepository(session),
                digest_repo=DigestRepository(session),
                audit_writer=AuditLogRepository(session).insert,
                model=s.openai.model,
                lookback_hours=hours,
                limit=s.candidate_limit,
                top_n=s.top_n,
            )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))
