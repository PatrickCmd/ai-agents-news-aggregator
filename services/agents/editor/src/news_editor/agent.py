"""Editor agent — per-user article ranker.

The model is passed as a string; the OpenAI Agents SDK selects the backend
(default: Responses API) — no manual `OpenAIChatCompletionsModel` wrapping.
"""

from __future__ import annotations

from agents import Agent
from news_schemas.agent_io import EditorDecision
from news_schemas.user_profile import UserProfile

from news_editor.prompts import build_system_prompt


def build_agent(*, profile: UserProfile, email_name: str, model: str) -> Agent[EditorDecision]:
    return Agent(
        name="EditorAgent",
        instructions=build_system_prompt(profile, email_name=email_name),
        model=model,
        output_type=EditorDecision,
    )
