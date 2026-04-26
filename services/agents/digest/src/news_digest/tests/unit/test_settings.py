from __future__ import annotations

import pytest


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGEST_MAX_CONTENT_CHARS", raising=False)
    from news_digest.settings import DigestSettings

    s = DigestSettings()
    assert s.max_content_chars == 8000


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGEST_MAX_CONTENT_CHARS", "1500")
    from news_digest.settings import DigestSettings

    s = DigestSettings()
    assert s.max_content_chars == 1500
