from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# The script lives outside the news_scraper package (in infra/), so load it manually.
_SCRIPT = Path(__file__).resolve().parents[6] / "infra" / "scraper" / "sync_secrets.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_secrets", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_secrets"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_env_to_param_map_covers_8_secrets() -> None:
    mod = _load_module()
    assert len(mod.ENV_TO_PARAM) == 8
    assert "SUPABASE_DB_URL" in mod.ENV_TO_PARAM
    assert "OPENAI_API_KEY" in mod.ENV_TO_PARAM
    assert mod.ENV_TO_PARAM["SUPABASE_DB_URL"] == "supabase_db_url"


def test_push_params_calls_put_parameter_for_each_set_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()
    for key in list(mod.ENV_TO_PARAM.keys()):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")  # pragma: allowlist secret
    monkeypatch.setenv("RESEND_API_KEY", "re_fake")  # pragma: allowlist secret

    fake_ssm = MagicMock()
    count = mod.push_params(fake_ssm, env="dev")

    assert count == 3
    assert fake_ssm.put_parameter.call_count == 3
    names = {call.kwargs["Name"] for call in fake_ssm.put_parameter.call_args_list}
    assert names == {
        "/news-aggregator/dev/supabase_db_url",
        "/news-aggregator/dev/openai_api_key",
        "/news-aggregator/dev/resend_api_key",
    }
    for call in fake_ssm.put_parameter.call_args_list:
        assert call.kwargs["Type"] == "SecureString"
        assert call.kwargs["Overwrite"] is True
