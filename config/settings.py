"""Configuration settings loaded from environment variables."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)   # Load env vars from .env, but don't override existing ones (like OPENAI_API_KEY)


class YouTubeProxySettings:
    """Settings for YouTube transcript proxy configuration."""

    def __init__(self):
        """Load proxy settings from environment variables."""
        self.enabled = os.getenv("YOUTUBE_PROXY_ENABLED", "false").lower() == "true"
        self.username = os.getenv("YOUTUBE_PROXY_USERNAME")
        self.password = os.getenv("YOUTUBE_PROXY_PASSWORD")

    @property
    def is_configured(self) -> bool:
        """Check if proxy is properly configured."""
        return self.enabled and bool(self.username) and bool(self.password)

    def __repr__(self) -> str:
        """String representation (hides credentials)."""
        if self.is_configured:
            return (
                f"YouTubeProxySettings(enabled=True, username={self.username[:4]}***)"
            )
        return "YouTubeProxySettings(enabled=False)"


class OpenAISettings:
    """Settings for OpenAI API configuration."""

    def __init__(self):
        """Load OpenAI API settings from environment variables."""
        self.api_key = os.getenv("OPENAI_API_KEY")

    @property
    def is_configured(self) -> bool:
        """Check if OpenAI API is properly configured."""
        return bool(self.api_key)

    def __repr__(self) -> str:
        """String representation (hides API key)."""
        if self.is_configured:
            return f"OpenAISettings(configured=True, key={self.api_key[:7]}***)"
        return "OpenAISettings(configured=False)"


# Global settings instances
youtube_proxy = YouTubeProxySettings()
openai_settings = OpenAISettings()