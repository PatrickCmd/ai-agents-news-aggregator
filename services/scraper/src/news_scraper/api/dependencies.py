"""FastAPI DI helpers."""

from __future__ import annotations

from news_config.loader import SourcesConfig, load_sources
from news_config.settings import (
    AppSettings,
    LangfuseSettings,
    OpenAISettings,
    YouTubeProxySettings,
)
from news_db.engine import get_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from news_scraper.settings import ScraperSettings


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a sessionmaker bound to the singleton engine.

    Used by background tasks which outlive the request lifecycle.
    """
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False)


def get_sources() -> SourcesConfig:
    return load_sources()


def get_scraper_settings() -> ScraperSettings:
    return ScraperSettings()


def get_openai_settings() -> OpenAISettings:
    return OpenAISettings()


def get_app_settings() -> AppSettings:
    return AppSettings()


def get_langfuse_settings() -> LangfuseSettings:
    return LangfuseSettings()


def get_youtube_proxy_settings() -> YouTubeProxySettings:
    return YouTubeProxySettings()
