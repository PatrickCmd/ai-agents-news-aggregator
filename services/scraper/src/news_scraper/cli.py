"""Typer CLI. Same pipeline code as the HTTP API; blocks until completion."""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import typer
from news_db.engine import get_session
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_observability.logging import setup_logging
from news_schemas.scraper_run import PipelineName, ScraperRunIn, ScraperRunStatus

from news_scraper.api.routes import _run_background  # reuse server plumbing

app = typer.Typer(no_args_is_help=True, help="News scraper CLI")


def _exit_code_for(status: ScraperRunStatus) -> int:
    if status is ScraperRunStatus.SUCCESS:
        return 0
    if status is ScraperRunStatus.PARTIAL:
        return 1
    if status is ScraperRunStatus.FAILED:
        return 2
    return 3


async def _start_and_run(pipelines: list[PipelineName], lookback_hours: int) -> ScraperRunStatus:
    setup_logging()
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        started = await repo.start(
            ScraperRunIn(
                trigger="cli",
                lookback_hours=lookback_hours,
                pipelines_requested=pipelines,
            )
        )
    await _run_background(
        run_id=started.id,
        lookback_hours=lookback_hours,
        pipeline_names=pipelines,
    )
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        final = await repo.get_by_id(started.id)
        typer.echo(f"run {started.id} -> {final.status.value if final else 'unknown'}")
        return final.status if final else ScraperRunStatus.FAILED


@app.command()
def ingest(lookback_hours: int = 24) -> None:
    """Run all three pipelines."""
    status = asyncio.run(
        _start_and_run(
            [PipelineName.YOUTUBE, PipelineName.RSS, PipelineName.WEB_SEARCH],
            lookback_hours,
        )
    )
    sys.exit(_exit_code_for(status))


@app.command("ingest-youtube")
def ingest_youtube(lookback_hours: int = 24) -> None:
    """Run YouTube pipeline only."""
    sys.exit(_exit_code_for(asyncio.run(_start_and_run([PipelineName.YOUTUBE], lookback_hours))))


@app.command("ingest-rss")
def ingest_rss(lookback_hours: int = 24) -> None:
    """Run RSS pipeline only."""
    sys.exit(_exit_code_for(asyncio.run(_start_and_run([PipelineName.RSS], lookback_hours))))


@app.command("ingest-web")
def ingest_web(lookback_hours: int = 48) -> None:
    """Run web-search pipeline only."""
    sys.exit(_exit_code_for(asyncio.run(_start_and_run([PipelineName.WEB_SEARCH], lookback_hours))))


@app.command()
def runs(limit: int = 20) -> None:
    """Show recent scraper runs."""

    async def _main() -> None:
        async with get_session() as session:
            repo = ScraperRunRepository(session)
            for r in await repo.get_recent(limit=limit):
                typer.echo(
                    f"{r.id}  {r.started_at.isoformat()}  {r.status.value:8}  "
                    f"{' '.join(p.value for p in r.pipelines_requested)}"
                )

    asyncio.run(_main())


@app.command("run-show")
def run_show(run_id: UUID) -> None:
    """Show a single run as JSON."""

    async def _main() -> None:
        async with get_session() as session:
            repo = ScraperRunRepository(session)
            r = await repo.get_by_id(run_id)
            if r is None:
                typer.echo(f"run {run_id} not found", err=True)
                sys.exit(2)
            typer.echo(r.model_dump_json(indent=2))

    asyncio.run(_main())


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI server (uvicorn)."""
    import uvicorn

    uvicorn.run("news_scraper.main:app", host=host, port=port)
