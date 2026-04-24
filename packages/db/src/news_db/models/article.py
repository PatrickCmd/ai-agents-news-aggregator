from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_db.models.base import Base, TimestampMixin


class Article(Base, TimestampMixin):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "source_type in ('rss','youtube','web_search')",
            name="articles_source_type_check",
        ),
        UniqueConstraint("source_type", "external_id", name="articles_source_external_uk"),
        Index("ix_articles_source_pub", "source_type", "published_at"),
        Index("ix_articles_pub", "published_at"),
    )
