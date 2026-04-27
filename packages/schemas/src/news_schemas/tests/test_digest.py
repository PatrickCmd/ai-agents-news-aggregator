from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from news_schemas.digest import DigestIn, DigestOut, DigestStatus, RankedArticle


def test_ranked_article_score_bounds():
    RankedArticle(article_id=1, score=0, title="t", url="https://u", summary="s", why_ranked="w")
    RankedArticle(article_id=1, score=100, title="t", url="https://u", summary="s", why_ranked="w")
    with pytest.raises(ValidationError):
        RankedArticle(
            article_id=1,
            score=101,
            title="t",
            url="https://u",
            summary="s",
            why_ranked="w",
        )


def test_digest_in_rejects_more_than_10_ranked():
    items = [
        RankedArticle(
            article_id=i,
            score=50,
            title=f"t{i}",
            url="https://u",
            summary="s",
            why_ranked="w",
        )
        for i in range(11)
    ]
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        DigestIn(
            user_id=uuid4(),
            period_start=now,
            period_end=now,
            intro=None,
            ranked_articles=items,
            top_themes=[],
            article_count=11,
            status=DigestStatus.PENDING,
        )


def test_digest_out_round_trip():
    now = datetime.now(UTC)
    d = DigestOut(
        id=1,
        user_id=uuid4(),
        period_start=now,
        period_end=now,
        intro="hi",
        ranked_articles=[],
        top_themes=[],
        article_count=0,
        status=DigestStatus.GENERATED,
        error_message=None,
        generated_at=now,
    )
    assert d.status == DigestStatus.GENERATED


def test_digest_summary_out_excludes_ranked_articles():
    from news_schemas.digest import DigestSummaryOut

    payload = {
        "id": 17,
        "user_id": uuid4(),
        "period_start": datetime(2026, 4, 26, tzinfo=UTC),
        "period_end": datetime(2026, 4, 27, tzinfo=UTC),
        "intro": "Hi there",
        "top_themes": ["agents", "infra"],
        "article_count": 7,
        "status": DigestStatus.GENERATED,
        "generated_at": datetime(2026, 4, 27, 5, 0, tzinfo=UTC),
    }
    summary = DigestSummaryOut.model_validate(payload)
    assert summary.id == 17
    assert summary.article_count == 7
    assert summary.intro == "Hi there"
    assert "ranked_articles" not in summary.model_dump()
    assert "error_message" not in summary.model_dump()


def test_digest_summary_out_intro_optional():
    from news_schemas.digest import DigestSummaryOut

    summary = DigestSummaryOut.model_validate(
        {
            "id": 18,
            "user_id": uuid4(),
            "period_start": datetime(2026, 4, 26, tzinfo=UTC),
            "period_end": datetime(2026, 4, 27, tzinfo=UTC),
            "intro": None,
            "top_themes": [],
            "article_count": 0,
            "status": DigestStatus.PENDING,
            "generated_at": datetime(2026, 4, 27, 5, 0, tzinfo=UTC),
        }
    )
    assert summary.intro is None
