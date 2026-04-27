"""ApiSettings: env-backed configuration for the API service."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    clerk_issuer: str = Field(
        ...,
        description="Clerk frontend API URL — used as the JWT 'iss' claim.",
    )
    clerk_jwks_url: str = Field(
        ...,
        description="Where to fetch Clerk's signing keys.",
    )
    remix_state_machine_arn: str = Field(
        ...,
        description="ARN of news-remix-user state machine (from #3).",
    )
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="CORS allowed origins (also configured at API Gateway).",
    )
    git_sha: str = Field(default="unknown", description="Surfaced via /healthz.")
    log_level: str = Field(default="INFO")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        # Lambda env vars are strings; turn comma-separated into a list.
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Cached settings loader — one instance per process."""
    return ApiSettings()
