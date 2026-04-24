"""HTTP routes: /ingest, /ingest/{pipeline}, /runs, /runs/{id}, /healthz."""

from __future__ import annotations

import os
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from news_db.engine import get_session
from news_db.repositories.article_repo import ArticleRepository
from news_db.repositories.audit_log_repo import AuditLogRepository
from news_db.repositories.scraper_run_repo import ScraperRunRepository
from news_observability.audit import AuditLogger
from news_observability.logging import get_logger
from news_schemas.scraper_run import (
    PipelineName,
    ScraperRunIn,
    ScraperRunOut,
)
from pydantic import BaseModel, Field

from news_scraper.api.dependencies import (
    get_openai_settings,
    get_scraper_settings,
    get_session_factory,
    get_sources,
    get_youtube_proxy_settings,
)
from news_scraper.mcp_servers import create_rss_mcp_server
from news_scraper.orchestrator import run_all
from news_scraper.pipelines.base import Pipeline
from news_scraper.pipelines.rss import RSSPipeline
from news_scraper.pipelines.rss_adapters import MCPFeedFetcher
from news_scraper.pipelines.web_search import WebSearchPipeline
from news_scraper.pipelines.web_search_adapters import PlaywrightAgentCrawler
from news_scraper.pipelines.youtube import YouTubePipeline
from news_scraper.pipelines.youtube_adapters import (
    FeedparserYouTubeFeedFetcher,
    YouTubeTranscriptApiFetcher,
)

_log = get_logger("api")
router = APIRouter()


class IngestRequest(BaseModel):
    lookback_hours: int = Field(default=24, ge=1, le=168)
    trigger: str = Field(default="api", pattern="^(api|cli|scheduler)$")


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "git_sha": os.environ.get("GIT_SHA", "unknown")}


@router.post("/ingest", status_code=202)
async def ingest_all(
    req: IngestRequest,
    background: BackgroundTasks,
) -> ScraperRunOut:
    return await _launch(
        [PipelineName.YOUTUBE, PipelineName.RSS, PipelineName.WEB_SEARCH],
        req,
        background,
    )


@router.post("/ingest/youtube", status_code=202)
async def ingest_youtube(req: IngestRequest, background: BackgroundTasks) -> ScraperRunOut:
    return await _launch([PipelineName.YOUTUBE], req, background)


@router.post("/ingest/rss", status_code=202)
async def ingest_rss(req: IngestRequest, background: BackgroundTasks) -> ScraperRunOut:
    return await _launch([PipelineName.RSS], req, background)


@router.post("/ingest/web-search", status_code=202)
async def ingest_web_search(req: IngestRequest, background: BackgroundTasks) -> ScraperRunOut:
    return await _launch([PipelineName.WEB_SEARCH], req, background)


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID) -> ScraperRunOut:
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        row = await repo.get_by_id(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        return row


@router.get("/runs")
async def list_runs(limit: int = 20) -> list[ScraperRunOut]:
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        return await repo.get_recent(limit=limit)


async def _launch(
    pipelines: list[PipelineName],
    req: IngestRequest,
    background: BackgroundTasks,
) -> ScraperRunOut:
    async with get_session() as session:
        repo = ScraperRunRepository(session)
        started = await repo.start(
            ScraperRunIn(
                trigger=req.trigger,
                lookback_hours=req.lookback_hours,
                pipelines_requested=pipelines,
            )
        )
    background.add_task(
        _run_background,
        run_id=started.id,
        lookback_hours=req.lookback_hours,
        pipeline_names=pipelines,
    )
    return started


async def _run_background(
    *,
    run_id: UUID,
    lookback_hours: int,
    pipeline_names: list[PipelineName],
) -> None:
    """Executed by FastAPI BackgroundTasks. Builds pipelines + calls run_all.

    The RSS pipeline owns an MCP subprocess whose lifetime must wrap the whole
    pipeline run, so we enter `create_rss_mcp_server` here (and only when RSS
    is requested) and perform `run_all` inside the async-with block.
    """
    session_factory = get_session_factory()
    sources = get_sources()
    scraper_settings = get_scraper_settings()
    openai_settings = get_openai_settings()
    yt_proxy = get_youtube_proxy_settings()

    async with session_factory() as session:
        article_repo = ArticleRepository(session)
        run_repo = ScraperRunRepository(session)
        audit_repo = AuditLogRepository(session)
        audit_logger = AuditLogger(audit_repo.insert)

        non_rss_pipelines: list[Pipeline] = []

        if PipelineName.YOUTUBE in pipeline_names and sources.youtube_enabled:
            non_rss_pipelines.append(
                YouTubePipeline(
                    fetcher=FeedparserYouTubeFeedFetcher(),
                    transcripts=YouTubeTranscriptApiFetcher(
                        proxy_enabled=yt_proxy.enabled,
                        proxy_username=yt_proxy.username,
                        proxy_password=yt_proxy.password,
                    ),
                    repo=article_repo,
                    channels=sources.youtube_channels,
                    transcript_concurrency=scraper_settings.youtube_transcript_concurrency,
                )
            )

        if (
            PipelineName.WEB_SEARCH in pipeline_names
            and sources.web_search is not None
            and sources.web_search.enabled
        ):
            non_rss_pipelines.append(
                WebSearchPipeline(
                    crawler=PlaywrightAgentCrawler(
                        model=openai_settings.model,
                        max_turns=scraper_settings.web_search_max_turns,
                        site_timeout=scraper_settings.web_search_site_timeout,
                    ),
                    repo=article_repo,
                    audit_logger=audit_logger,
                    sites=sources.web_search.sites,
                    site_concurrency=sources.web_search.max_concurrent_sites,
                    run_id=run_id,
                )
            )

        rss_requested = (
            PipelineName.RSS in pipeline_names and sources.rss is not None and sources.rss.enabled
        )

        if rss_requested:
            assert sources.rss is not None  # for type narrowing
            async with create_rss_mcp_server(
                scraper_settings.rss_mcp_path,
                timeout_seconds=sources.rss.mcp_timeout_seconds,
            ) as mcp_server:
                rss_pipeline = RSSPipeline(
                    fetcher=MCPFeedFetcher(mcp_server),
                    repo=article_repo,
                    feeds=sources.rss.feeds,
                    feed_concurrency=sources.rss.max_concurrent_feeds,
                )
                await run_all(
                    run_id=run_id,
                    lookback_hours=lookback_hours,
                    pipelines=[*non_rss_pipelines, rss_pipeline],
                    repo=run_repo,
                )
        else:
            await run_all(
                run_id=run_id,
                lookback_hours=lookback_hours,
                pipelines=non_rss_pipelines,
                repo=run_repo,
            )
