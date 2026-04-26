from __future__ import annotations

import pytest

from news_config.settings import MailSettings


def test_mail_settings_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIL_FROM", "noreply@news.example.com")
    monkeypatch.setenv("SENDER_NAME", "Custom Sender")
    monkeypatch.setenv("MAIL_TO_DEFAULT", "p@example.com")
    s = MailSettings()
    assert s.mail_from == "noreply@news.example.com"
    assert s.sender_name == "Custom Sender"
    assert s.mail_to_default == "p@example.com"
    assert s.is_configured is True


def test_mail_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("SENDER_NAME", raising=False)
    monkeypatch.delenv("MAIL_TO_DEFAULT", raising=False)
    s = MailSettings()
    assert s.mail_from == ""
    assert s.sender_name == "AI News Digest"
    assert s.mail_to_default == ""
    assert s.is_configured is False
