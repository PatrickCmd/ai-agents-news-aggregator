"""Cold-start helper to read SSM SecureStrings into env vars (Lambda)."""

from __future__ import annotations

import os
from typing import Any

from news_observability.logging import get_logger

_log = get_logger("lambda_settings")


def load_settings_from_ssm(
    *,
    prefix: str,
    ssm_client: Any | None = None,
) -> None:
    """Populate env vars from an SSM parameter tree.

    Idempotent: bails out as soon as one canary env var (SUPABASE_DB_URL) is
    set. Pass an explicit ``ssm_client`` to mock during tests.

    Calls ``os.environ.setdefault`` so existing env vars (e.g. local .env) win.
    """
    if os.environ.get("SUPABASE_DB_URL"):
        return

    if ssm_client is None:
        import boto3  # local import — keeps pure-Python tests fast

        ssm_client = boto3.client("ssm")

    resp = ssm_client.get_parameters_by_path(Path=prefix, WithDecryption=True, Recursive=True)
    for p in resp.get("Parameters", []):
        env_key = p["Name"].rsplit("/", 1)[-1].upper()
        os.environ.setdefault(env_key, p["Value"])
    _log.info("loaded {} ssm params from {}", len(resp.get("Parameters", [])), prefix)
