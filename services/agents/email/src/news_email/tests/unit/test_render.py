from __future__ import annotations

from news_schemas.agent_io import EmailIntroduction
from news_schemas.digest import RankedArticle


def _intro() -> EmailIntroduction:
    # Note: avoid apostrophes in fixture strings — autoescape converts them to
    # `&#39;` and would break substring assertions. The XSS-escape test below
    # is the regression guard that proves autoescape is enabled.
    return EmailIntroduction(
        greeting="Hi Pat,",
        introduction="Welcome to the daily digest. Lots happening in agents land.",
        highlight="The biggest story is the new Agents SDK release.",
        subject_line="AI Daily — agents go GA",
    )


def _ranked() -> list[RankedArticle]:
    return [
        RankedArticle(
            article_id=1,
            score=92,
            title="Agents SDK GA",
            url="https://example.com/1",
            summary="The Agents SDK is generally available.",
            why_ranked="Direct match for your interest in agent orchestration.",
        )
    ]


def test_render_includes_intro_and_articles() -> None:
    from news_email.render import render_digest_html

    html = render_digest_html(_intro(), _ranked(), top_themes=["agents"])
    assert "Hi Pat," in html
    assert "Welcome to the daily digest" in html
    assert "Agents SDK GA" in html
    assert "https://example.com/1" in html
    assert "agents" in html


def test_render_handles_zero_articles() -> None:
    from news_email.render import render_digest_html

    html = render_digest_html(_intro(), [], top_themes=[])
    assert "Hi Pat," in html
    assert "<article" not in html


def test_render_escapes_html_in_user_content() -> None:
    """Jinja2 autoescape must HTML-escape article content (XSS prevention)."""
    from news_email.render import render_digest_html

    intro = EmailIntroduction(
        greeting="Hi <script>alert(1)</script>,",
        introduction="Welcome to today's digest. Lots happening in agents land.",
        highlight="The biggest story is the new Agents SDK release.",
        subject_line="AI Daily",
    )
    ranked = [
        RankedArticle(
            article_id=1,
            score=50,
            title="<img src=x onerror=alert(1)>",
            url="https://example.com/1",
            summary="<b>injected</b>",
            why_ranked="match",
        )
    ]
    html = render_digest_html(intro, ranked, top_themes=[])
    # Autoescape must convert dangerous chars
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html
