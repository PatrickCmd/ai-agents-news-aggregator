from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from news_schemas.digest import DigestIn, DigestOut, DigestStatus, RankedArticle


def test_ranked_article_score_bounds():
    RankedArticle(
        article_id=1, score=0, title="t", url="https://u", summary="s", why_ranked="w"
    )
    RankedArticle(
        article_id=1, score=100, title="t", url="https://u", summary="s", why_ranked="w"
    )
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
    now = datetime.now(timezone.utc)
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
    now = datetime.now(timezone.utc)
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
