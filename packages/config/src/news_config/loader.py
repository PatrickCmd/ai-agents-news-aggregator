"""YAML loader: sources.yml (scraper config) and user_profile.yml (seed user)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from news_schemas.user_profile import UserProfile

_PKG_DIR = Path(__file__).parent


@dataclass(frozen=True)
class SourcesConfig:
    default_hours: int
    youtube_enabled: bool
    youtube_channels: list[dict[str, str]] = field(default_factory=list)
    openai_enabled: bool = False
    anthropic_enabled: bool = False
    anthropic_feed_types: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def load_sources(path: Path | None = None) -> SourcesConfig:
    path = path or (_PKG_DIR / "sources.yml")
    data: dict[str, Any] = yaml.safe_load(path.read_text())
    yt = data.get("youtube", {})
    oa = data.get("openai", {})
    an = data.get("anthropic", {})
    return SourcesConfig(
        default_hours=int(data.get("default_hours", 24)),
        youtube_enabled=bool(yt.get("enabled", False)),
        youtube_channels=list(yt.get("channels", [])),
        openai_enabled=bool(oa.get("enabled", False)),
        anthropic_enabled=bool(an.get("enabled", False)),
        anthropic_feed_types=list(an.get("feed_types", [])),
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
