from __future__ import annotations

import pytest


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EDITOR_CANDIDATE_LIMIT", raising=False)
    monkeypatch.delenv("EDITOR_TOP_N", raising=False)
    from news_editor.settings import EditorSettings

    s = EditorSettings()
    assert s.candidate_limit == 100
    assert s.top_n == 10


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITOR_CANDIDATE_LIMIT", "50")
    monkeypatch.setenv("EDITOR_TOP_N", "5")
    from news_editor.settings import EditorSettings

    s = EditorSettings()
    assert s.candidate_limit == 50
    assert s.top_n == 5
