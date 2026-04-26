from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from news_schemas.agent_io import DigestSummary
from news_schemas.article import ArticleOut, SourceType
from news_schemas.audit import AuditLogIn


@dataclass
class _Usage:
    input_tokens: int = 100
    output_tokens: int = 50
    total_tokens: int = 150
    requests: int = 1


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: DigestSummary
    context_wrapper: _Wrapper


class _CapturingArticleRepo:
    def __init__(self, article: ArticleOut | None) -> None:
        self._article = article
        self.updates: list[tuple[int, str]] = []

    async def get_by_id(self, article_id: int) -> ArticleOut | None:
        return self._article

    async def update_summary(self, article_id: int, summary: str) -> None:
        self.updates.append((article_id, summary))


class _CapturingAuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditLogIn] = []

    async def insert(self, entry: AuditLogIn) -> None:
        self.entries.append(entry)


def _article(*, summary: str | None, content_text: str | None = "x" * 200) -> ArticleOut:
    return ArticleOut(
        id=42,
        source_type=SourceType.RSS,
        source_name="t",
        external_id="ext-1",
        title="t",
        url="https://x",
        author=None,
        published_at=datetime.now(UTC),
        content_text=content_text,
        summary=summary,
        tags=[],
        raw={},
        fetched_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _dummy_summary() -> DigestSummary:
    return DigestSummary(
        summary="A useful summary that is long enough to satisfy the schema. " * 2,
        key_takeaways=["one", "two"],
    )


@pytest.mark.asyncio
async def test_summarize_skips_when_summary_already_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(_article(summary="already done"))
    audit = _CapturingAuditRepo()

    called = False

    async def _fake_runner_run(agent, input):  # noqa: A002
        nonlocal called
        called = True
        return _FakeResult(_dummy_summary(), _Wrapper(_Usage()))

    monkeypatch.setattr("news_digest.pipeline.Runner.run", _fake_runner_run)

    out = await p.summarize_article(
        article_id=42,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["skipped"] is True
    assert called is False
    assert repo.updates == []
    assert audit.entries == []


@pytest.mark.asyncio
async def test_summarize_skips_when_no_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(_article(summary=None, content_text=None))
    audit = _CapturingAuditRepo()

    out = await p.summarize_article(
        article_id=42,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["skipped"] is True
    assert out["reason"] == "no content_text"
    assert repo.updates == []


@pytest.mark.asyncio
async def test_summarize_writes_summary_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(_article(summary=None))
    audit = _CapturingAuditRepo()
    canned = _dummy_summary()

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(canned, _Wrapper(_Usage()))

    monkeypatch.setattr("news_digest.pipeline.Runner.run", _fake_runner_run)

    out = await p.summarize_article(
        article_id=42,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["skipped"] is False
    assert repo.updates == [(42, canned.summary)]
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry.metadata["article_id"] == 42
    assert entry.metadata["model"] == "gpt-5.4-mini"
    assert entry.metadata["input_tokens"] == 100


@pytest.mark.asyncio
async def test_summarize_returns_error_when_article_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_digest import pipeline as p

    repo = _CapturingArticleRepo(article=None)
    audit = _CapturingAuditRepo()

    out = await p.summarize_article(
        article_id=99,
        article_repo=repo,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        max_content_chars=8000,
    )
    assert out["error"] == "not found"
    assert audit.entries == []
