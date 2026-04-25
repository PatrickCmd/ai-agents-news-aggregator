"""FastAPI app factory with startup logging, tracing, orphan sweep."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from news_db.engine import get_session
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_observability.logging import get_logger, setup_logging
from news_observability.tracing import configure_tracing

from news_scraper.api.routes import router

_log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    configure_tracing(enable_langfuse=True)
    try:
        async with get_session() as session:
            repo = ScraperRunRepository(session)
            count = await repo.mark_orphaned(older_than=datetime.now(UTC) - timedelta(hours=2))
            if count:
                _log.info("orphan sweep flipped {} stale scraper_runs rows", count)
    except Exception as exc:  # DB may be unreachable at first boot
        _log.warning("orphan sweep skipped: {}", exc)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="news-scraper", lifespan=lifespan)
    app.include_router(router)
    return app


app = create_app()
