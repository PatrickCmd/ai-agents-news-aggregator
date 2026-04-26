from __future__ import annotations

from news_schemas.user_profile import (
    Interests,
    Preferences,
    ReadingTime,
    UserProfile,
)


def _profile() -> UserProfile:
    return UserProfile(
        background=["dev"],
        interests=Interests(primary=["AI"]),
        preferences=Preferences(),
        goals=[],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )


def test_build_agent_returns_agent_with_editor_decision_output_type() -> None:
    from news_schemas.agent_io import EditorDecision

    from news_editor.agent import build_agent

    agent = build_agent(profile=_profile(), email_name="Pat", model="gpt-5.4-mini")
    assert agent.output_type is EditorDecision
    assert agent.name == "EditorAgent"


def test_build_agent_passes_model_string_through() -> None:
    """Pass the model as a string — let the SDK pick the backend (default: Responses API)."""
    from news_editor.agent import build_agent

    agent = build_agent(profile=_profile(), email_name="Pat", model="gpt-5.4-mini")
    assert agent.model == "gpt-5.4-mini"


def test_build_agent_embeds_profile_in_instructions() -> None:
    """The system prompt embeds the reader's email_name and profile fields."""
    from news_editor.agent import build_agent

    profile = UserProfile(
        background=[],
        interests=Interests(primary=["RAG"]),
        preferences=Preferences(),
        goals=["build agents"],
        reading_time=ReadingTime(daily_limit="20m", preferred_article_count="5"),
    )
    agent = build_agent(profile=profile, email_name="Pat", model="gpt-5.4-mini")
    assert "Pat" in agent.instructions
    assert "RAG" in agent.instructions
    assert "build agents" in agent.instructions
