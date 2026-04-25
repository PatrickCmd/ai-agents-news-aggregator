from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SCRIPT = Path(__file__).resolve().parents[6] / "services" / "scraper" / "deploy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("deploy", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deploy"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_tf_dir_points_at_scraper_module() -> None:
    mod = _load_module()
    assert mod._terraform_dir().name == "scraper"
    assert mod._terraform_dir().parent.name == "infra"


def test_cmd_deploy_calls_terraform_workspace_and_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_module()

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(mod, "cmd_build", lambda: 0)
    monkeypatch.setattr(mod, "_smoke_healthz", lambda url: None)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    rc = mod.cmd_deploy(env="dev")

    assert rc == 0
    assert any(c[0:3] == ["terraform", "workspace", "select"] for c in calls)
    apply_calls = [c for c in calls if c[0:2] == ["terraform", "apply"]]
    assert len(apply_calls) == 1
    apply_cmd = apply_calls[0]
    assert "-auto-approve" in apply_cmd
    assert any(a.startswith("-var=image_tag=") for a in apply_cmd)
    # Deliberately NO -replace flag (in-place updates avoid INACTIVE retention).
    assert not any(a.startswith("-replace=") for a in apply_cmd)
