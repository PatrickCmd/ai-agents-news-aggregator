"""Digest agent — per-article LLM summariser.

The model is passed as a string; the OpenAI Agents SDK selects the backend
(default: Responses API) — no manual `OpenAIChatCompletionsModel` wrapping.
"""

from __future__ import annotations

from agents import Agent
from news_observability.sanitizer import sanitize_prompt_input
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
    """Build the user prompt for the digest agent.

    Sanitises *content*, *title*, and *source_name* via
    `sanitize_prompt_input` before embedding — these are scraped from
    third-party feeds and could contain prompt-injection payloads.
    Hard-block patterns (e.g. ``<|im_start|>``) raise PromptInjectionError;
    soft-block patterns (e.g. "ignore previous instructions") are silently
    redacted.
    """
    safe_title = sanitize_prompt_input(title)
    safe_source_name = sanitize_prompt_input(source_name)
    safe_content = sanitize_prompt_input(content) if content else ""
    truncated = safe_content[:max_chars]
    return (
        f"Article source: {source_type} — {safe_source_name}\n"
        f"Original title: {safe_title}\n"
        f"URL: {url}\n\n"
        f"CONTENT:\n{truncated}"
    )
