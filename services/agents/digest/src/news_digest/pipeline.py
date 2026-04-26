"""Digest pipeline — summarise one article."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any, Protocol

from agents import Runner, trace
from news_observability.audit import AuditLogger
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.validators import validate_structured_output
from news_schemas.agent_io import DigestSummary
from news_schemas.article import ArticleOut
from news_schemas.audit import AgentName, AuditLogIn, DecisionType

from news_digest.agent import build_agent, build_user_prompt

_log = get_logger("digest_pipeline")

AuditWriter = Callable[[AuditLogIn], Awaitable[None]]


class _ArticleRepo(Protocol):
    async def get_by_id(self, article_id: int) -> ArticleOut | None: ...
    async def update_summary(self, article_id: int, summary: str) -> None: ...


async def summarize_article(
    *,
    article_id: int,
    article_repo: _ArticleRepo,
    audit_writer: AuditWriter,
    model: str,
    max_content_chars: int,
) -> dict[str, Any]:
    """Summarise one article. Idempotent: skips when summary already populated."""

    article = await article_repo.get_by_id(article_id)
    if article is None:
        return {"article_id": article_id, "error": "not found"}
    if article.summary is not None:
        return {"article_id": article_id, "skipped": True}
    if not article.content_text:
        return {
            "article_id": article_id,
            "skipped": True,
            "reason": "no content_text",
        }

    agent = build_agent(model=model)
    prompt = build_user_prompt(
        title=article.title,
        url=str(article.url),
        source_type=article.source_type.value,
        source_name=article.source_name,
        content=article.content_text,
        max_chars=max_content_chars,
    )
    t0 = perf_counter()
    with trace(f"digest.{article_id}"):
        result = await Runner.run(agent, input=prompt)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    digest = validate_structured_output(DigestSummary, result.final_output)
    usage = extract_usage(result, model=model)

    await article_repo.update_summary(article_id, digest.summary)

    audit = AuditLogger(audit_writer)
    await audit.log_decision(
        agent_name=AgentName.DIGEST,
        user_id=None,
        decision_type=DecisionType.SUMMARY,
        input_text=f"article {article_id}: {article.title}",
        output_text=digest.summary,
        metadata={
            "article_id": article_id,
            "key_takeaways": digest.key_takeaways,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "requests": usage.requests,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "duration_ms": elapsed_ms,
        },
    )

    return {
        "article_id": article_id,
        "summary": digest.summary,
        "skipped": False,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "duration_ms": elapsed_ms,
    }
