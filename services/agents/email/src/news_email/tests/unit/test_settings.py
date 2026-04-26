from __future__ import annotations

import pytest


def test_settings_composes_subsettings(monkeypatch: pytest.MonkeyPatch) -> None:
    # Import first so news_config.settings runs load_dotenv, then clear env to
    # exercise true defaults regardless of the developer's local .env.
    from news_email.settings import EmailSettings

    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("SENDER_NAME", raising=False)
    monkeypatch.delenv("MAIL_TO_DEFAULT", raising=False)

    s = EmailSettings()
    # Composition smoke: each sub-settings is its default-factory instance.
    assert s.openai.model == "gpt-5.4-mini"
    assert s.resend.api_key == ""
    assert s.mail.sender_name == "AI News Digest"


def test_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", "re_test_123")  # pragma: allowlist secret
    monkeypatch.setenv("MAIL_FROM", "hi@example.com")
    monkeypatch.setenv("SENDER_NAME", "Test Sender")
    from news_email.settings import EmailSettings

    s = EmailSettings()
    assert s.resend.api_key == "re_test_123"  # pragma: allowlist secret
    assert s.resend.is_configured is True
    assert s.mail.mail_from == "hi@example.com"
    assert s.mail.sender_name == "Test Sender"
    assert s.mail.is_configured is True
