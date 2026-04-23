"""Base scraper abstract class."""

from abc import ABC, abstractmethod
from typing import Any


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""

    @abstractmethod
    def scrape(self, **kwargs) -> list[dict[str, Any]]:
        """
        Scrape content from the source.

        Returns:
            List of dictionaries containing scraped data
        """
        pass

    @abstractmethod
    def validate_source(self, source: str) -> bool:
        """
        Validate that the source identifier is valid.

        Args:
            source: Source identifier (e.g., channel ID, URL)

        Returns:
            True if valid, False otherwise
        """
        pass