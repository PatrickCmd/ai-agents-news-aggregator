from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from news_schemas.article import ArticleIn, ArticleOut, SourceType


def test_source_type_members():
    assert SourceType.RSS.value == "rss"
    assert SourceType.YOUTUBE.value == "youtube"
    assert SourceType.WEB_SEARCH.value == "web_search"


def test_article_in_minimal_valid():
    a = ArticleIn(
        source_type=SourceType.RSS,
        source_name="openai_news",
        external_id="abc-123",
        title="Hello",
        url="https://example.com/a",
    )
    assert a.tags == []
    assert a.raw == {}


def test_article_in_rejects_empty_title():
    with pytest.raises(ValidationError):
        ArticleIn(
            source_type=SourceType.RSS,
            source_name="openai_news",
            external_id="abc-123",
            title="",
            url="https://example.com/a",
        )


def test_article_out_has_id_and_timestamps():
    now = datetime.now(UTC)
    a = ArticleOut(
        id=1,
        source_type=SourceType.YOUTUBE,
        source_name="Anthropic",
        external_id="vid123",
        title="t",
        url="https://yt/v",
        author=None,
        published_at=None,
        content_text=None,
        summary=None,
        tags=[],
        raw={},
        fetched_at=now,
        created_at=now,
        updated_at=now,
    )
    assert a.id == 1
    assert a.source_type == SourceType.YOUTUBE
