from __future__ import annotations

import pytest
from pydantic import ValidationError

from news_schemas.agent_io import (
    ArticleRanking,
    DigestSummary,
    EditorDecision,
    EmailIntroduction,
)


def test_digest_summary_valid() -> None:
    s = DigestSummary(
        summary="A " + ("very useful summary " * 5),
        key_takeaways=["t1", "t2"],
    )
    assert s.summary.startswith("A ")
    assert len(s.key_takeaways) == 2


def test_digest_summary_rejects_short_summary() -> None:
    with pytest.raises(ValidationError):
        DigestSummary(summary="short", key_takeaways=[])


def test_digest_summary_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DigestSummary.model_validate(
            {
                "summary": "x" * 60,
                "key_takeaways": [],
                "unexpected": "nope",
            }
        )


def test_article_ranking_score_bounds() -> None:
    ArticleRanking(article_id=1, score=0, why_ranked="ten chars long", key_topics=[])
    ArticleRanking(article_id=1, score=100, why_ranked="ten chars long", key_topics=[])
    with pytest.raises(ValidationError):
        ArticleRanking(article_id=1, score=101, why_ranked="ten chars long", key_topics=[])


def test_editor_decision_valid() -> None:
    d = EditorDecision(
        rankings=[
            ArticleRanking(article_id=1, score=80, why_ranked="ten chars long", key_topics=["x"])
        ],
        top_themes=["theme"],
        overall_summary="all good",
    )
    assert len(d.rankings) == 1


def test_email_introduction_valid() -> None:
    e = EmailIntroduction(
        greeting="Hi Pat,",
        introduction="Welcome to today's digest. Lots happening in agents land.",
        highlight="The biggest story is the new Agents SDK release.",
        subject_line="AI Daily — agents go GA",
    )
    assert e.subject_line.startswith("AI Daily")
