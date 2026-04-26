"""Local Typer CLI for the digest agent."""

from __future__ import annotations

import asyncio
import sys

import typer
from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_observability.logging import setup_logging

from news_digest.pipeline import summarize_article
from news_digest.settings import DigestSettings

app = typer.Typer(no_args_is_help=True, help="Digest agent CLI")


@app.command()
def summarize(article_id: int) -> None:
    """Summarise one article by ID."""

    async def _run() -> int:
        setup_logging()
        s = DigestSettings()
        async with get_session() as session:
            article_repo = ArticleRepository(session)
            audit_repo = AuditLogRepository(session)
            out = await summarize_article(
                article_id=article_id,
                article_repo=article_repo,
                audit_writer=audit_repo.insert,
                model=s.openai.model,
                max_content_chars=s.max_content_chars,
            )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command()
def sweep(hours: int = 24, limit: int = 50) -> None:
    """Summarise all unsummarised articles published within `hours`."""

    async def _run() -> int:
        setup_logging()
        s = DigestSettings()
        async with get_session() as session:
            article_repo = ArticleRepository(session)
            audit_repo = AuditLogRepository(session)
            pending = await article_repo.get_unsummarized(hours=hours, limit=limit)
            typer.echo(f"sweeping {len(pending)} unsummarised articles")
            for art in pending:
                out = await summarize_article(
                    article_id=art.id,
                    article_repo=article_repo,
                    audit_writer=audit_repo.insert,
                    model=s.openai.model,
                    max_content_chars=s.max_content_chars,
                )
                typer.echo(f"{art.id}: {out.get('skipped', False)}")
        return 0

    sys.exit(asyncio.run(_run()))
