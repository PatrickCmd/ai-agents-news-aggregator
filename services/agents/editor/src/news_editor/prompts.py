"""System prompt + candidate prompt for the editor agent."""

from __future__ import annotations

from typing import Any

from news_observability.sanitizer import sanitize_prompt_input
from news_schemas.user_profile import UserProfile


def build_system_prompt(profile: UserProfile, *, email_name: str) -> str:
    return (
        f"You are a personalised AI news editor for {email_name}.\n\n"
        f"Reader profile:\n"
        f"- Background: {', '.join(profile.background) or 'n/a'}\n"
        f"- Primary interests: {', '.join(profile.interests.primary) or 'n/a'}\n"
        f"- Secondary interests: {', '.join(profile.interests.secondary) or 'n/a'}\n"
        f"- Specific topics: {', '.join(profile.interests.specific_topics) or 'n/a'}\n"
        f"- Preferred content: {', '.join(profile.preferences.content_type) or 'any'}\n"
        f"- Avoid: {', '.join(profile.preferences.avoid) or 'nothing'}\n"
        f"- Goals: {', '.join(profile.goals) or 'n/a'}\n"
        f"- Reading time: {profile.reading_time.daily_limit}\n\n"
        "Score every candidate article on a 0-100 scale (relevance to the "
        "reader's profile and goals). Emit `rankings` (one entry per article), "
        "`top_themes` (up to 10 short phrases describing the day's pattern), "
        "and a brief `overall_summary`.\n\n"
        "Rules:\n"
        "- Only return article_ids that appeared in the candidate list.\n"
        "- `why_ranked` is 1-2 sentences explaining the score for that reader.\n"
        "- Penalise items that match `avoid`. Reward items that match interests "
        "AND content preferences.\n"
        "- Be ruthless: there should be a wide score spread."
    )


def build_candidate_prompt(candidates: list[dict[str, Any]]) -> str:
    """Build the candidate-list prompt for the editor agent.

    Sanitises *title*, *summary*, *source_name* per AGENTS.md prompt-injection
    invariant — these are scraped third-party text. Hard-block patterns raise
    PromptInjectionError; soft-block patterns are silently redacted.
    """
    lines = ["Candidates (id | source | title | summary):"]
    for c in candidates:
        title = sanitize_prompt_input((c.get("title") or "").strip())
        summary = sanitize_prompt_input((c.get("summary") or "").strip())
        source = sanitize_prompt_input(c.get("source_name") or "")
        lines.append(f"- {c['id']} | {source} | {title} | {summary}")
    lines.append("")
    lines.append("Score each. Use the article_id field exactly as given.")
    return "\n".join(lines)
