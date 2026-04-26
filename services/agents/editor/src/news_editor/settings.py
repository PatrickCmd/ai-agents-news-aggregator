"""Editor-agent-specific settings, layered on top of news_config."""

from __future__ import annotations

from news_config.settings import OpenAISettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EditorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    candidate_limit: int = Field(default=100, alias="EDITOR_CANDIDATE_LIMIT")
    top_n: int = Field(default=10, alias="EDITOR_TOP_N")
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
