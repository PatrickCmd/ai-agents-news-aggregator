from __future__ import annotations

import pytest


def test_scheduler_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGEST_SWEEP_LIMIT", raising=False)
    monkeypatch.delenv("DIGEST_SWEEP_HOURS", raising=False)
    from news_scheduler.settings import SchedulerSettings

    s = SchedulerSettings()
    assert s.digest_sweep_limit == 200
    assert s.digest_sweep_hours == 24


def test_scheduler_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGEST_SWEEP_LIMIT", "50")
    monkeypatch.setenv("DIGEST_SWEEP_HOURS", "12")
    from news_scheduler.settings import SchedulerSettings

    s = SchedulerSettings()
    assert s.digest_sweep_limit == 50
    assert s.digest_sweep_hours == 12
