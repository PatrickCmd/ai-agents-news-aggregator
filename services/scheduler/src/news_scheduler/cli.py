"""Local Typer CLI for the scheduler list handlers (dev-only — no AWS calls)."""

from __future__ import annotations

import asyncio
import sys

import typer
from news_observability.logging import setup_logging

from news_scheduler.handlers import (
    list_active_users,
    list_new_digests,
    list_unsummarised,
)
from news_scheduler.settings import SchedulerSettings

app = typer.Typer(no_args_is_help=True, help="Scheduler CLI")


@app.callback()
def _root() -> None:
    """Force Typer subcommand routing even when commands are added one-by-one."""


@app.command("list-unsummarised")
def list_unsummarised_cmd(hours: int = 24, limit: int = 200) -> None:
    """Print article IDs without a summary (digest stage input)."""

    async def _run() -> int:
        setup_logging()
        s = SchedulerSettings()
        out = await list_unsummarised.run(
            hours=hours or s.digest_sweep_hours,
            limit=limit or s.digest_sweep_limit,
        )
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command("list-active-users")
def list_active_users_cmd() -> None:
    """Print active user IDs (editor stage input)."""

    async def _run() -> int:
        setup_logging()
        out = await list_active_users.run()
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))


@app.command("list-new-digests")
def list_new_digests_cmd() -> None:
    """Print today's GENERATED digest IDs (email stage input)."""

    async def _run() -> int:
        setup_logging()
        out = await list_new_digests.run()
        typer.echo(out)
        return 0

    sys.exit(asyncio.run(_run()))
