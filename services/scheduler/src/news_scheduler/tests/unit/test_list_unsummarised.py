from __future__ import annotations

from datetime import UTC, datetime

import pytest
from news_schemas.article import ArticleOut, SourceType


def _article(aid: int) -> ArticleOut:
    return ArticleOut(
        id=aid,
        source_type=SourceType.RSS,
        source_name="src",
        external_id=f"ext-{aid}",
        title=f"T{aid}",
        url=f"https://x/{aid}",
        author=None,
        published_at=datetime.now(UTC),
        content_text="c",
        summary=None,
        tags=[],
        raw={},
        fetched_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _CapturingArticleRepo:
    def __init__(self, rows: list[ArticleOut]) -> None:
        self._rows = rows
        self.calls: list[tuple[int, int]] = []

    async def get_unsummarized(self, hours: int, limit: int = 50) -> list[ArticleOut]:
        self.calls.append((hours, limit))
        return self._rows


@pytest.mark.asyncio
async def test_list_unsummarised_returns_article_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_unsummarised

    repo = _CapturingArticleRepo([_article(1), _article(2), _article(3)])

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    def _fake_get_session() -> _FakeSession:
        return _FakeSession()

    monkeypatch.setattr(list_unsummarised, "get_session", _fake_get_session)
    monkeypatch.setattr(list_unsummarised, "ArticleRepository", lambda s: repo)

    out = await list_unsummarised.run(hours=24, limit=200)
    assert out == {"article_ids": [1, 2, 3]}
    assert repo.calls == [(24, 200)]


@pytest.mark.asyncio
async def test_list_unsummarised_returns_empty_when_no_articles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_scheduler.handlers import list_unsummarised

    repo = _CapturingArticleRepo([])

    class _FakeSession:
        async def __aenter__(self) -> _FakeSession:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    monkeypatch.setattr(list_unsummarised, "get_session", lambda: _FakeSession())
    monkeypatch.setattr(list_unsummarised, "ArticleRepository", lambda s: repo)

    out = await list_unsummarised.run(hours=24, limit=200)
    assert out == {"article_ids": []}
