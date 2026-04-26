"""Jinja2 renderer for the digest email."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from news_schemas.agent_io import EmailIntroduction
from news_schemas.digest import RankedArticle

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
# Note: Jinja2's select_autoescape does endswith matching against the full
# template name. Our template is `digest.html.j2` — listing only "html"
# would NOT activate autoescape (the file ends in .j2, not .html).
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)

_ALLOWED_URL_SCHEMES = ("http://", "https://")


def render_digest_html(
    intro: EmailIntroduction,
    ranked_articles: list[RankedArticle],
    top_themes: list[str],
) -> str:
    """Render the digest email HTML.

    Jinja2 ``select_autoescape(["html", "j2"])`` is enabled — every
    interpolation of `intro`, `article`, `top_themes` is HTML-escaped. This
    blocks XSS via LLM-generated text or scraped article content.

    Defense-in-depth: rejects ranked articles whose URL doesn't use http(s).
    Upstream `HttpUrl` validation already enforces this, but a future caller
    using `RankedArticle.model_construct` would bypass it; the render-time
    check keeps the contract local.

    Raises:
        ValueError: if any ranked article has a non-http(s) URL scheme.
    """
    for r in ranked_articles:
        if not str(r.url).startswith(_ALLOWED_URL_SCHEMES):
            raise ValueError(
                f"Refusing to render non-http(s) URL: {r.url} (article_id={r.article_id})"
            )

    template = _env.get_template("digest.html.j2")
    return template.render(
        greeting=intro.greeting,
        introduction=intro.introduction,
        highlight=intro.highlight,
        ranked_articles=[r.model_dump(mode="json") for r in ranked_articles],
        top_themes=top_themes,
    )
