"""Email agent — composes a personalised intro + subject for the digest.

The model is passed as a string; the OpenAI Agents SDK selects the backend
(default: Responses API) — no manual `OpenAIChatCompletionsModel` wrapping.
"""

from __future__ import annotations

from agents import Agent
from news_observability.sanitizer import sanitize_prompt_input
from news_schemas.agent_io import EmailIntroduction

_INSTRUCTIONS = (
    "You are an email composer for a personalised AI news digest. Given the "
    "reader's name, profile, and a ranked list of articles, produce:\n"
    "- greeting: short, friendly, addresses the reader by name\n"
    "- introduction: 2-4 sentences setting up today's digest, written for this "
    "reader's interests\n"
    "- highlight: 1-2 sentences calling out the single most important story\n"
    "- subject_line: punchy, under 120 chars, mentions the top theme\n\n"
    "Tone: warm, smart, never hype. No emojis."
)


def build_agent(*, model: str) -> Agent[EmailIntroduction]:
    return Agent(
        name="EmailAgent",
        instructions=_INSTRUCTIONS,
        model=model,
        output_type=EmailIntroduction,
    )


def build_email_prompt(
    *, email_name: str, top_themes: list[str], ranked: list[dict[str, object]]
) -> str:
    """Build the user prompt for the email agent.

    Sanitises article *title* and *summary* (scraped third-party text) per the
    AGENTS.md prompt-injection invariant. Hard-block patterns raise
    PromptInjectionError; soft-block patterns are silently redacted. Themes
    and `why_ranked` are LLM-generated upstream so are passed through as-is.
    """
    lines = [
        f"Reader: {email_name}",
        f"Top themes today: {', '.join(top_themes) or 'n/a'}",
        "Ranked articles (highest first):",
    ]
    for r in ranked:
        safe_title = sanitize_prompt_input(str(r["title"]))
        safe_summary = sanitize_prompt_input(str(r["summary"]))
        lines.append(f"- [{r['score']}] {safe_title} — {safe_summary} (why: {r['why_ranked']})")
    lines.append("")
    lines.append("Compose greeting, introduction, highlight, and subject_line.")
    return "\n".join(lines)
