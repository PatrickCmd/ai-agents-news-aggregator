"""Jinja2 renderer for the digest email."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from news_schemas.agent_io import EmailIntroduction
from news_schemas.digest import RankedArticle

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
# Enable autoescape for both `.html` and `.j2` since our template filename is
# `digest.html.j2` — Jinja2 dispatches autoescape via `endswith` on the full
# template name, so we must list `j2` to catch templates ending in `.j2`.
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)


def render_digest_html(
    intro: EmailIntroduction,
    ranked_articles: list[RankedArticle],
    top_themes: list[str],
) -> str:
    """Render the digest email HTML.

    Jinja2 ``select_autoescape(["html"])`` is enabled — every interpolation
    of `intro`, `article`, `top_themes` is HTML-escaped. This blocks XSS via
    LLM-generated text or scraped article content.
    """
    template = _env.get_template("digest.html.j2")
    return template.render(
        greeting=intro.greeting,
        introduction=intro.introduction,
        highlight=intro.highlight,
        ranked_articles=[r.model_dump(mode="json") for r in ranked_articles],
        top_themes=top_themes,
    )
