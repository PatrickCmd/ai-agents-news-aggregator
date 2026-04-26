from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from news_schemas.agent_io import ArticleRanking, EditorDecision
from news_schemas.article import ArticleOut, SourceType
from news_schemas.audit import AuditLogIn
from news_schemas.digest import DigestIn, DigestOut, DigestStatus
from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserOut,
    UserProfile,
)


@dataclass
class _Usage:
    input_tokens: int = 200
    output_tokens: int = 100
    total_tokens: int = 300
    requests: int = 1


@dataclass
class _Wrapper:
    usage: _Usage


@dataclass
class _FakeResult:
    final_output: object  # EditorDecision or garbage dict
    context_wrapper: _Wrapper


def _profile() -> UserProfile:
    return UserProfile(
        background=["dev"],
        interests=Interests(primary=["agents"]),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


def _user(uid: UUID) -> UserOut:
    return UserOut(
        id=uid,
        clerk_user_id="c-1",
        email="t@example.com",
        name="t",
        email_name="Pat",
        profile=_profile(),
        profile_completed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


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
        summary=f"summary {aid}",
        tags=[],
        raw={},
        fetched_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _CapturingDigestRepo:
    def __init__(self) -> None:
        self.created: list[DigestIn] = []
        self._next_id = 100

    async def create(self, d: DigestIn) -> DigestOut:
        self.created.append(d)
        out = DigestOut(
            id=self._next_id,
            user_id=d.user_id,
            period_start=d.period_start,
            period_end=d.period_end,
            intro=d.intro,
            ranked_articles=d.ranked_articles,
            top_themes=d.top_themes,
            article_count=d.article_count,
            status=d.status,
            error_message=d.error_message,
            generated_at=datetime.now(UTC),
        )
        self._next_id += 1
        return out


class _ArticleRepo:
    def __init__(self, rows: list[ArticleOut]) -> None:
        self._rows = rows

    async def get_recent_with_summaries(self, hours: int, limit: int) -> list[ArticleOut]:
        return self._rows[:limit]


class _UserRepo:
    def __init__(self, user: UserOut | None) -> None:
        self._user = user

    async def get_by_id(self, user_id: UUID) -> UserOut | None:
        return self._user


class _AuditRepo:
    def __init__(self) -> None:
        self.entries: list[AuditLogIn] = []

    async def insert(self, e: AuditLogIn) -> None:
        self.entries.append(e)


@pytest.mark.asyncio
async def test_rank_for_user_no_candidates_writes_failed_digest() -> None:
    from news_editor import pipeline

    uid = uuid4()
    digests = _CapturingDigestRepo()

    out = await pipeline.rank_for_user(
        user_id=uid,
        article_repo=_ArticleRepo([]),
        user_repo=_UserRepo(_user(uid)),
        digest_repo=digests,
        audit_writer=_AuditRepo().insert,
        model="gpt-5.4-mini",
        lookback_hours=24,
        limit=100,
        top_n=10,
    )
    assert digests.created[0].status is DigestStatus.FAILED
    assert digests.created[0].error_message == "no candidates"
    assert out["digest_id"] == 100
    assert out["status"] == "failed"


@pytest.mark.asyncio
async def test_rank_for_user_drops_hallucinated_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from news_editor import pipeline

    uid = uuid4()
    candidates = [_article(1), _article(2)]

    canned = EditorDecision(
        rankings=[
            ArticleRanking(article_id=1, score=80, why_ranked="ten chars long"),
            ArticleRanking(article_id=999, score=99, why_ranked="ten chars long"),
            ArticleRanking(article_id=2, score=60, why_ranked="ten chars long"),
        ],
        top_themes=["t"],
        overall_summary="",
    )

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(canned, _Wrapper(_Usage()))

    monkeypatch.setattr("news_editor.pipeline.Runner.run", _fake_runner_run)

    digests = _CapturingDigestRepo()
    audit = _AuditRepo()
    out = await pipeline.rank_for_user(
        user_id=uid,
        article_repo=_ArticleRepo(candidates),
        user_repo=_UserRepo(_user(uid)),
        digest_repo=digests,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        lookback_hours=24,
        limit=100,
        top_n=10,
    )
    assert digests.created[0].status is DigestStatus.GENERATED
    ids = [r.article_id for r in digests.created[0].ranked_articles]
    assert 999 not in ids
    assert ids == [1, 2]
    assert audit.entries
    assert out["digest_id"] == 100


@pytest.mark.asyncio
async def test_rank_for_user_raises_when_user_missing() -> None:
    from news_editor import pipeline

    with pytest.raises(ValueError, match="not found"):
        await pipeline.rank_for_user(
            user_id=uuid4(),
            article_repo=_ArticleRepo([]),
            user_repo=_UserRepo(None),
            digest_repo=_CapturingDigestRepo(),
            audit_writer=_AuditRepo().insert,
            model="gpt-5.4-mini",
            lookback_hours=24,
            limit=100,
            top_n=10,
        )


@pytest.mark.asyncio
async def test_rank_for_user_handles_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §9: structured-output validation failure is a business failure.

    Audit row written with output_summary='validation_failed';
    digest row written with status='failed', error_message='validation';
    return dict has failed=True, no exception raised.
    """
    from news_editor import pipeline

    uid = uuid4()
    candidates = [_article(1)]

    # final_output garbage: rankings list is too long (max_length=100; pass 200).
    bad_output = {
        "rankings": [{"article_id": 1, "score": 50, "why_ranked": "ten chars long"}] * 200,
        "top_themes": [],
        "overall_summary": "",
    }

    async def _fake_runner_run(agent, input):  # noqa: A002
        return _FakeResult(bad_output, _Wrapper(_Usage()))

    monkeypatch.setattr("news_editor.pipeline.Runner.run", _fake_runner_run)

    digests = _CapturingDigestRepo()
    audit = _AuditRepo()
    out = await pipeline.rank_for_user(
        user_id=uid,
        article_repo=_ArticleRepo(candidates),
        user_repo=_UserRepo(_user(uid)),
        digest_repo=digests,
        audit_writer=audit.insert,
        model="gpt-5.4-mini",
        lookback_hours=24,
        limit=100,
        top_n=10,
    )
    assert out["failed"] is True
    assert out["reason"] == "validation"
    assert digests.created[0].status is DigestStatus.FAILED
    assert digests.created[0].error_message == "validation"
    assert any(e.output_summary == "validation_failed" for e in audit.entries)
