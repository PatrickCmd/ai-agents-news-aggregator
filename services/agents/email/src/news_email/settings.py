"""Email-agent-specific settings, layered on top of news_config."""

from __future__ import annotations

from news_config.settings import MailSettings, OpenAISettings, ResendSettings
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    resend: ResendSettings = Field(default_factory=ResendSettings)
    mail: MailSettings = Field(default_factory=MailSettings)
