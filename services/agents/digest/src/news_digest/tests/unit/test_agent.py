from __future__ import annotations


def test_build_agent_returns_agent_with_digest_summary_output_type() -> None:
    from news_schemas.agent_io import DigestSummary

    from news_digest.agent import build_agent

    agent = build_agent(model="gpt-5.4-mini")
    assert agent.output_type is DigestSummary
    assert agent.name == "DigestAgent"


def test_build_agent_passes_model_string_through() -> None:
    """Pass the model as a string — let the SDK pick the backend (default: Responses API)."""
    from news_digest.agent import build_agent

    agent = build_agent(model="gpt-5.4-mini")
    assert agent.model == "gpt-5.4-mini"
