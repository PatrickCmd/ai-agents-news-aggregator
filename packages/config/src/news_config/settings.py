"""Env-backed settings using pydantic-settings."""

from __future__ import annotations

from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(override=False)


class _Base(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")


class DatabaseSettings(_Base):
    supabase_db_url: str = Field(default="", alias="SUPABASE_DB_URL")
    supabase_pooler_url: str = Field(default="", alias="SUPABASE_POOLER_URL")


class OpenAISettings(_Base):
    api_key: str = Field(default="", alias="OPENAI_API_KEY")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


class LangfuseSettings(_Base):
    public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    @property
    def is_configured(self) -> bool:
        return bool(self.public_key) and bool(self.secret_key)


class YouTubeProxySettings(_Base):
    enabled: bool = Field(default=False, alias="YOUTUBE_PROXY_ENABLED")
    username: str = Field(default="", alias="YOUTUBE_PROXY_USERNAME")
    password: str = Field(default="", alias="YOUTUBE_PROXY_PASSWORD")

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.username) and bool(self.password)


class ResendSettings(_Base):
    api_key: str = Field(default="", alias="RESEND_API_KEY")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


class AppSettings(_Base):
    env: Literal["dev", "staging", "prod"] = Field(default="dev", alias="ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
