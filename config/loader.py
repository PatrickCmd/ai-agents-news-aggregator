"""Configuration loader for the AI News Aggregator."""

import sys
from pathlib import Path
from typing import Any

import yaml

# Add project root to path if running directly
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.logging import get_logger

logger = get_logger(__name__)


class Config:
    """Configuration manager for the AI News Aggregator."""

    def __init__(self, config_path: str | None = None):
        """
        Initialize configuration from YAML file.

        Args:
            config_path: Path to config file. If None, uses default config/sources.yaml
        """
        if config_path is None:
            config_path = project_root / "config" / "sources.yaml"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self._config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {self.config_path}")
                return config
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {self.config_path}")
            return self._get_default_config()
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration: {str(e)}")
            return self._get_default_config()

    def _get_default_config(self) -> dict[str, Any]:
        """Get default configuration if config file is not available."""
        logger.warning("Using default configuration")
        return {
            "default_hours": 24,
            "youtube": {"enabled": True, "channels": []},
            "openai": {"enabled": True},
            "anthropic": {
                "enabled": True,
                "feed_types": ["news", "engineering", "research", "red_team"],
            },
        }

    @property
    def default_hours(self) -> int:
        """Get default lookback period in hours."""
        return self._config.get("default_hours", 24)

    @property
    def youtube_enabled(self) -> bool:
        """Check if YouTube scraping is enabled."""
        return self._config.get("youtube", {}).get("enabled", False)

    @property
    def youtube_channels(self) -> list[str]:
        """Get list of YouTube channel IDs to monitor."""
        channels = self._config.get("youtube", {}).get("channels", [])
        return [channel["channel_id"] for channel in channels]

    @property
    def youtube_channel_names(self) -> dict[str, str]:
        """Get mapping of channel IDs to channel names."""
        channels = self._config.get("youtube", {}).get("channels", [])
        return {channel["channel_id"]: channel["name"] for channel in channels}

    @property
    def openai_enabled(self) -> bool:
        """Check if OpenAI scraping is enabled."""
        return self._config.get("openai", {}).get("enabled", False)

    @property
    def anthropic_enabled(self) -> bool:
        """Check if Anthropic scraping is enabled."""
        return self._config.get("anthropic", {}).get("enabled", False)

    @property
    def anthropic_feed_types(self) -> list[str]:
        """Get list of Anthropic feed types to scrape."""
        return self._config.get("anthropic", {}).get(
            "feed_types", ["news", "engineering", "research", "red_team"]
        )

    def reload(self):
        """Reload configuration from file."""
        logger.info("Reloading configuration")
        self._config = self._load_config()


# Global config instance
_config: Config | None = None


def get_config(config_path: str | None = None) -> Config:
    """
    Get global configuration instance.

    Args:
        config_path: Path to config file. Only used on first call.

    Returns:
        Config instance
    """
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config


if __name__ == "__main__":
    # Example usage
    config = get_config()

    print("\n" + "=" * 80)
    print("CONFIGURATION")
    print("=" * 80 + "\n")

    print(f"Default hours: {config.default_hours}")
    print()

    print(f"YouTube enabled: {config.youtube_enabled}")
    print(f"YouTube channels: {len(config.youtube_channels)}")
    for channel_id in config.youtube_channels:
        name = config.youtube_channel_names.get(channel_id, "Unknown")
        print(f"  - {name} ({channel_id})")
    print()

    print(f"OpenAI enabled: {config.openai_enabled}")
    print()

    print(f"Anthropic enabled: {config.anthropic_enabled}")
    print(f"Anthropic feed types: {config.anthropic_feed_types}")
    print()