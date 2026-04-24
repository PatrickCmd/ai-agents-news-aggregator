from __future__ import annotations

import pytest

from news_config.settings import OpenAISettings


def test_model_defaults_to_gpt_5_4_mini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    s = OpenAISettings()
    assert s.model == "gpt-5.4-mini"


def test_model_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4")
    s = OpenAISettings()
    assert s.model == "gpt-5.4"
