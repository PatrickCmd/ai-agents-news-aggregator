"""Editor pipeline — score candidates and write a `digests` row."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

from agents import Runner, trace
from news_observability.audit import AuditLogger
from news_observability.costs import extract_usage
from news_observability.logging import get_logger
from news_observability.validators import StructuredOutputError, validate_structured_output
from news_schemas.agent_io import EditorDecision
from news_schemas.article import ArticleOut
from news_schemas.audit import AgentName, AuditLogIn, DecisionType
from news_schemas.digest import DigestIn, DigestOut, DigestStatus, RankedArticle
from news_schemas.user_profile import UserOut

from news_editor.agent import build_agent
from news_editor.prompts import build_candidate_prompt

_log = get_logger("editor_pipeline")
AuditWriter = Callable[[AuditLogIn], Awaitable[None]]


class _ArticleRepo(Protocol):
    async def get_recent_with_summaries(self, hours: int, limit: int) -> list[ArticleOut]: ...


class _UserRepo(Protocol):
    async def get_by_id(self, user_id: UUID) -> UserOut | None: ...


class _DigestRepo(Protocol):
    async def create(self, item: DigestIn) -> DigestOut: ...


async def rank_for_user(
    *,
    user_id: UUID,
    article_repo: _ArticleRepo,
    user_repo: _UserRepo,
    digest_repo: _DigestRepo,
    audit_writer: AuditWriter,
    model: str,
    lookback_hours: int,
    limit: int,
    top_n: int,
) -> dict[str, Any]:
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise ValueError(f"user {user_id} not found")

    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(hours=lookback_hours)

    candidates = await article_repo.get_recent_with_summaries(hours=lookback_hours, limit=limit)

    if not candidates:
        _log.info("editor skip: no candidates for user {}", user_id)
        digest = await digest_repo.create(
            DigestIn(
                user_id=user_id,
                period_start=period_start,
                period_end=period_end,
                ranked_articles=[],
                article_count=0,
                status=DigestStatus.FAILED,
                error_message="no candidates",
            )
        )
        return {"digest_id": digest.id, "status": DigestStatus.FAILED.value}

    agent = build_agent(profile=user.profile, email_name=user.email_name, model=model)
    prompt_payload = [
        {
            "id": a.id,
            "title": a.title,
            "summary": a.summary or "",
            "source_name": a.source_name,
            "url": a.url,
        }
        for a in candidates
    ]
    prompt = build_candidate_prompt(prompt_payload)

    t0 = perf_counter()
    with trace(f"editor.user.{user_id}"):
        result = await Runner.run(agent, input=prompt)
    elapsed_ms = int((perf_counter() - t0) * 1000)

    audit = AuditLogger(audit_writer)
    usage = extract_usage(result, model=model)

    try:
        decision = validate_structured_output(EditorDecision, result.final_output)
    except StructuredOutputError as exc:
        _log.error("editor validation_failed for user {}: {}", user_id, exc)
        digest = await digest_repo.create(
            DigestIn(
                user_id=user_id,
                period_start=period_start,
                period_end=period_end,
                ranked_articles=[],
                article_count=len(candidates),
                status=DigestStatus.FAILED,
                error_message="validation",
            )
        )
        await audit.log_decision(
            agent_name=AgentName.EDITOR,
            user_id=user_id,
            decision_type=DecisionType.RANK,
            input_text=f"user {user_id}: ranking {len(candidates)} candidates",
            output_text="validation_failed",
            metadata={
                "user_id": str(user_id),
                "candidate_count": len(candidates),
                "model": usage.model,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "requests": usage.requests,
                "estimated_cost_usd": usage.estimated_cost_usd,
                "duration_ms": elapsed_ms,
                "error": str(exc),
            },
        )
        return {
            "digest_id": digest.id,
            "failed": True,
            "reason": "validation",
        }

    by_id = {a.id: a for a in candidates}
    valid = [r for r in decision.rankings if r.article_id in by_id]
    if len(valid) < len(decision.rankings):
        _log.warning(
            "dropped {} hallucinated article_ids",
            len(decision.rankings) - len(valid),
        )
    top = sorted(valid, key=lambda r: r.score, reverse=True)[:top_n]

    ranked = [
        RankedArticle(
            article_id=r.article_id,
            score=r.score,
            title=by_id[r.article_id].title,
            url=by_id[r.article_id].url,  # type: ignore[arg-type]
            summary=by_id[r.article_id].summary or "",
            why_ranked=r.why_ranked,
        )
        for r in top
    ]

    digest_status = DigestStatus.GENERATED if ranked else DigestStatus.FAILED
    digest = await digest_repo.create(
        DigestIn(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            ranked_articles=ranked,
            top_themes=decision.top_themes,
            article_count=len(candidates),
            status=digest_status,
            error_message=None if ranked else "no valid rankings",
        )
    )

    await audit.log_decision(
        agent_name=AgentName.EDITOR,
        user_id=user_id,
        decision_type=DecisionType.RANK,
        input_text=f"user {user_id}: ranking {len(candidates)} candidates",
        output_text=(
            f"top pick art {top[0].article_id if top else None}; themes {decision.top_themes}"
        ),
        metadata={
            "user_id": str(user_id),
            "candidate_count": len(candidates),
            "top_pick_id": top[0].article_id if top else None,
            "top_themes": decision.top_themes,
            "model": usage.model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "requests": usage.requests,
            "estimated_cost_usd": usage.estimated_cost_usd,
            "duration_ms": elapsed_ms,
        },
    )
    _log.info(
        "editor ok: user {} ranked {} candidates → top {} (digest {})",
        user_id,
        len(candidates),
        len(ranked),
        digest.id,
    )

    return {"digest_id": digest.id, "status": digest_status.value, "ranked": len(ranked)}
