"""Digest agent — per-article LLM summariser.

The model is passed as a string; the OpenAI Agents SDK selects the backend
(default: Responses API) — no manual `OpenAIChatCompletionsModel` wrapping.
"""

from __future__ import annotations

from agents import Agent
from news_schemas.agent_io import DigestSummary

_INSTRUCTIONS = (
    "You are an expert AI news analyst and summariser. Your role is to create "
    "concise, engaging digest summaries of AI-related content (YouTube videos, "
    "blog posts, articles).\n\n"
    "Your task:\n"
    "1. Write a 2-3 sentence summary (50-500 chars) highlighting the key points, "
    "why it's significant, and practical impact.\n"
    "2. List 0-5 key takeaways, one short phrase each.\n\n"
    "Focus on technical accuracy, key insights, and actionable takeaways. Avoid "
    "marketing fluff or hype."
)


def build_agent(*, model: str) -> Agent[DigestSummary]:
    return Agent(
        name="DigestAgent",
        instructions=_INSTRUCTIONS,
        model=model,
        output_type=DigestSummary,
    )


def build_user_prompt(
    *,
    title: str,
    url: str,
    source_type: str,
    source_name: str,
    content: str,
    max_chars: int,
) -> str:
    truncated = content[:max_chars] if content else ""
    return (
        f"Article source: {source_type} — {source_name}\n"
        f"Original title: {title}\n"
        f"URL: {url}\n\n"
        f"CONTENT:\n{truncated}"
    )
