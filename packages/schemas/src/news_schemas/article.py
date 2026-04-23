from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceType(str, Enum):
    RSS = "rss"
    YOUTUBE = "youtube"
    WEB_SEARCH = "web_search"


class ArticleIn(BaseModel):
    """Ingestion-side contract. Written by scrapers; consumed by ArticleRepository."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_type: SourceType
    source_name: str = Field(..., min_length=1)
    external_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    url: HttpUrl
    author: str | None = None
    published_at: datetime | None = None
    content_text: str | None = None
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class ArticleOut(BaseModel):
    """Read-side contract. Returned from ArticleRepository."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: SourceType
    source_name: str
    external_id: str
    title: str
    url: str
    author: str | None
    published_at: datetime | None
    content_text: str | None
    summary: str | None
    tags: list[str]
    raw: dict[str, Any]
    fetched_at: datetime
    created_at: datetime
    updated_at: datetime
