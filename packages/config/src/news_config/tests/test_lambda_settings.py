from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_load_settings_skips_when_db_url_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")
    from news_config.lambda_settings import load_settings_from_ssm

    fake = MagicMock()
    load_settings_from_ssm(prefix="/news-aggregator/dev", ssm_client=fake)
    fake.get_parameters_by_path.assert_not_called()


def test_load_settings_populates_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from news_config.lambda_settings import load_settings_from_ssm

    fake = MagicMock()
    fake.get_parameters_by_path.return_value = {
        "Parameters": [
            {
                "Name": "/news-aggregator/dev/openai_api_key",
                "Value": "sk-1",
            },  # pragma: allowlist secret
            {"Name": "/news-aggregator/dev/supabase_db_url", "Value": "url"},
        ]
    }
    load_settings_from_ssm(prefix="/news-aggregator/dev", ssm_client=fake)
    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-1"  # pragma: allowlist secret
    assert os.environ["SUPABASE_DB_URL"] == "url"
