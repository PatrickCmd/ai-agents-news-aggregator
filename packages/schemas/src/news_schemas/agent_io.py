"""LLM-side I/O schemas for the three agents.

LLM-side: every field is a primitive (str/int/list[str]/list[BaseModel]).
No HttpUrl, no EmailStr — Chat Completions structured outputs reject those.
URLs/emails are joined back from the DB after the LLM returns.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DigestSummary(BaseModel):
    """Output of the Digest agent for a single article."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=50, max_length=500)
    key_takeaways: list[str] = Field(default_factory=list, max_length=5)


class ArticleRanking(BaseModel):
    """One ranked article from the Editor agent."""

    model_config = ConfigDict(extra="forbid")

    article_id: int
    score: int = Field(..., ge=0, le=100)
    why_ranked: str = Field(..., min_length=10, max_length=300)
    key_topics: list[str] = Field(default_factory=list, max_length=5)


class EditorDecision(BaseModel):
    """Full output of the Editor agent for a user."""

    model_config = ConfigDict(extra="forbid")

    rankings: list[ArticleRanking] = Field(..., max_length=100)
    top_themes: list[str] = Field(default_factory=list, max_length=10)
    overall_summary: str = Field(default="", max_length=600)


class EmailIntroduction(BaseModel):
    """Output of the Email agent — the personalised intro + subject."""

    model_config = ConfigDict(extra="forbid")

    greeting: str = Field(..., min_length=5, max_length=100)
    introduction: str = Field(..., min_length=20, max_length=600)
    highlight: str = Field(..., min_length=10, max_length=300)
    subject_line: str = Field(..., min_length=5, max_length=120)
