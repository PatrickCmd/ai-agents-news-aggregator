from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ScraperRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class PipelineName(StrEnum):
    YOUTUBE = "youtube"
    RSS = "rss"
    WEB_SEARCH = "web_search"


class PipelineStats(BaseModel):
    status: ScraperRunStatus
    fetched: int = 0
    kept: int = 0
    inserted: int = 0
    skipped_old: int = 0
    duration_seconds: float = 0.0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class YouTubeStats(PipelineStats):
    transcripts_fetched: int = 0
    transcripts_failed: int = 0
    skipped_already_stored: int = 0


class WebSearchStats(PipelineStats):
    sites_attempted: int = 0
    sites_succeeded: int = 0
    items_extracted: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


class RunStats(BaseModel):
    youtube: YouTubeStats | None = None
    rss: PipelineStats | None = None
    web_search: WebSearchStats | None = None


class ScraperRunIn(BaseModel):
    trigger: str
    lookback_hours: int = 24
    pipelines_requested: list[PipelineName]


class ScraperRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trigger: str
    status: ScraperRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    lookback_hours: int
    pipelines_requested: list[PipelineName]
    stats: RunStats
    error_message: str | None = None
