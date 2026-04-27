"""ApiSettings: env-backed configuration for the API service."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import EnvSettingsSource


class CustomEnvSettingsSource(EnvSettingsSource):
    """Custom env source that handles CSV parsing for allowed_origins."""

    def prepare_field_value(
        self,
        field_name: str,
        field: Any,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        """Handle special parsing for allowed_origins field."""
        if field_name == "allowed_origins" and isinstance(value, str):
            # Don't let pydantic try to JSON-parse; return the string for validator
            return value
        return super().prepare_field_value(field_name, field, value, value_is_complex)


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
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="CORS allowed origins (also configured at API Gateway).",
    )
    git_sha: str = Field(default="unknown", description="Surfaced via /healthz.")
    log_level: str = Field(default="INFO")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """Use custom env source."""
        return (
            init_settings,
            CustomEnvSettingsSource(settings_cls),
            dotenv_settings,
            file_secret_settings,
        )

    def model_post_init(self, __context: Any) -> None:
        """Parse allowed_origins from string if needed."""
        # This runs after validation, so allowed_origins might still be a string
        if isinstance(self.allowed_origins, str):
            self.allowed_origins = [s.strip() for s in self.allowed_origins.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    """Cached settings loader — one instance per process."""
    return ApiSettings()  # type: ignore[call-arg]
