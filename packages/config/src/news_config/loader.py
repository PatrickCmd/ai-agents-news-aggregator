"""YAML loader: sources.yml (scraper config) and user_profile.yml (seed user)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from news_schemas.user_profile import UserProfile
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

_PKG_DIR = Path(__file__).parent


class RSSFeedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    url: HttpUrl


class RSSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    max_concurrent_feeds: int = 5
    mcp_timeout_seconds: int = 60
    feeds: list[RSSFeedConfig] = Field(default_factory=list)


class WebSearchSiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1)
    url: HttpUrl
    list_selector_hint: str = "Find recent posts listed on this blog page"


class WebSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    lookback_hours: int = 48
    max_concurrent_sites: int = 2
    sites: list[WebSearchSiteConfig] = Field(default_factory=list)


@dataclass(frozen=True)
class SourcesConfig:
    default_hours: int
    youtube_enabled: bool
    youtube_channels: list[dict[str, str]] = field(default_factory=list)
    openai_enabled: bool = False
    anthropic_enabled: bool = False
    anthropic_feed_types: list[str] = field(default_factory=list)
    rss: RSSConfig | None = None
    web_search: WebSearchConfig | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def load_sources(path: Path | None = None) -> SourcesConfig:
    path = path or (_PKG_DIR / "sources.yml")
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    yt = data.get("youtube", {})
    oa = data.get("openai", {})
    an = data.get("anthropic", {})

    rss_cfg = RSSConfig.model_validate(data["rss"]) if "rss" in data else None
    ws_cfg = WebSearchConfig.model_validate(data["web_search"]) if "web_search" in data else None

    return SourcesConfig(
        default_hours=int(data.get("default_hours", 24)),
        youtube_enabled=bool(yt.get("enabled", False)),
        youtube_channels=list(yt.get("channels", [])),
        openai_enabled=bool(oa.get("enabled", False)),
        anthropic_enabled=bool(an.get("enabled", False)),
        anthropic_feed_types=list(an.get("feed_types", [])),
        rss=rss_cfg,
        web_search=ws_cfg,
        raw=data,
    )


def load_user_profile_yaml(
    path: Path | None = None,
) -> tuple[UserProfile, dict[str, str]]:
    """Return (validated UserProfile, identity-level fields {name, email_name})."""
    path = path or (_PKG_DIR / "user_profile.yml")
    data = yaml.safe_load(path.read_text())
    user = data["user"]
    identity = {"name": user["name"], "email_name": user["email_name"]}
    profile_dict = {
        "background": user.get("background", []),
        "interests": user["interests"],
        "preferences": user["preferences"],
        "goals": user["goals"],
        "reading_time": user["reading_time"],
    }
    return UserProfile.model_validate(profile_dict), identity
