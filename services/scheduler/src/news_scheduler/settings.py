"""Scheduler-specific settings.

DB-only — no OpenAI / Resend / Jinja keys here. The scheduler's only job
is to query the DB for IDs and dispatch them via Step Functions.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    digest_sweep_limit: int = Field(default=200, alias="DIGEST_SWEEP_LIMIT")
    digest_sweep_hours: int = Field(default=24, alias="DIGEST_SWEEP_HOURS")
