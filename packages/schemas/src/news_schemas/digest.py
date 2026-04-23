from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class DigestStatus(str, Enum):
    PENDING = "pending"
    GENERATED = "generated"
    EMAILED = "emailed"
    FAILED = "failed"


class RankedArticle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: int
    score: int = Field(..., ge=0, le=100)
    title: str
    url: HttpUrl
    summary: str
    why_ranked: str


class DigestIn(BaseModel):
    user_id: UUID
    period_start: datetime
    period_end: datetime
    intro: str | None = None
    ranked_articles: list[RankedArticle] = Field(..., max_length=10)
    top_themes: list[str] = Field(default_factory=list)
    article_count: int = Field(..., ge=0)
    status: DigestStatus = DigestStatus.PENDING
    error_message: str | None = None


class DigestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: UUID
    period_start: datetime
    period_end: datetime
    intro: str | None
    ranked_articles: list[RankedArticle]
    top_themes: list[str]
    article_count: int
    status: DigestStatus
    error_message: str | None
    generated_at: datetime
