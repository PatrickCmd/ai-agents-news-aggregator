"""Digest-agent-specific settings, layered on top of news_config."""

from __future__ import annotations

from news_config.settings import OpenAISettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DigestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    max_content_chars: int = Field(default=8000, alias="DIGEST_MAX_CONTENT_CHARS")
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
