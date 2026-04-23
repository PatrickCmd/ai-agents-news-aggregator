"""YouTube RSS feed scraper with transcript extraction."""

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

import feedparser
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# Add project root to path if running directly
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scrapers.base import BaseScraper
from utils.logging import get_logger
from models.youtube import ChannelVideo, VideoTranscript, TranscriptSegment
from config.settings import youtube_proxy

logger = get_logger(__name__)


class YouTubeRSSScraper(BaseScraper):
    """Scraper for YouTube channels using RSS feeds."""

    RSS_URL_TEMPLATE = (
        "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    )

    def __init__(self, channel_ids: list[str]):
        """
        Initialize the YouTube RSS scraper.

        Args:
            channel_ids: List of YouTube channel IDs
        """
        self.channel_ids = channel_ids
        logger.info(f"Initialized YouTubeRSSScraper with {len(channel_ids)} channels")

        # Log proxy configuration status
        if youtube_proxy.is_configured:
            logger.info(
                f"YouTube transcript proxy ENABLED (Webshare, user: {youtube_proxy.username[:4]}***)"
            )
        else:
            logger.info(
                "YouTube transcript proxy DISABLED - may hit rate limits with high volume. "
                "See docs/YOUTUBE_TRANSCRIPTS.md for setup instructions."
            )

    def scrape(
        self, hours: int = 24, include_transcripts: bool = True
    ) -> list[ChannelVideo]:
        """
        Scrape videos from all configured channels.

        Args:
            hours: Only include videos from the last N hours (default: 24)
            include_transcripts: Whether to fetch transcripts (default: True)

        Returns:
            List of ChannelVideo objects with metadata and optional transcripts
        """
        logger.info(f"Starting scrape for videos from last {hours} hours")
        all_videos = []

        for channel_id in self.channel_ids:
            try:
                videos = self._scrape_channel(channel_id, hours, include_transcripts)
                all_videos.extend(videos)
                logger.info(
                    f"Found {len(videos)} recent videos from channel {channel_id}"
                )
            except Exception as e:
                logger.error(f"Error scraping channel {channel_id}: {str(e)}")
                continue

        logger.info(f"Total videos scraped: {len(all_videos)}")
        return all_videos

    def _scrape_channel(
        self, channel_id: str, hours: int, include_transcripts: bool
    ) -> list[ChannelVideo]:
        """
        Scrape a single YouTube channel.

        Args:
            channel_id: YouTube channel ID
            hours: Only include videos from the last N hours
            include_transcripts: Whether to fetch transcripts

        Returns:
            List of ChannelVideo objects
        """
        rss_url = self.RSS_URL_TEMPLATE.format(channel_id=channel_id)
        logger.debug(f"Fetching RSS feed: {rss_url}")

        feed = feedparser.parse(rss_url)

        if feed.bozo:
            logger.warning(
                f"RSS feed parsing error for {channel_id}: {feed.bozo_exception}"
            )

        if not feed.entries:
            logger.warning(f"No entries found in RSS feed for channel {channel_id}")
            return []

        videos = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        for entry in feed.entries:
            try:
                video_data = self._parse_entry(entry, channel_id)

                # Filter by time
                if video_data.published_at and video_data.published_at < cutoff_time:
                    logger.debug(
                        f"Skipping old video: {video_data.title} "
                        f"(published {video_data.published_at})"
                    )
                    continue

                # Optionally fetch transcript
                if include_transcripts:
                    transcript = self.get_transcript(video_data.video_id)
                    # Create a new ChannelVideo with transcript data
                    video_data = video_data.model_copy(
                        update={
                            "transcript": transcript,
                            "has_transcript": transcript is not None,
                        }
                    )
                else:
                    video_data = video_data.model_copy(
                        update={"transcript": None, "has_transcript": None}
                    )

                videos.append(video_data)

            except Exception as e:
                logger.error(f"Error parsing entry: {str(e)}")
                continue

        return videos

    def _parse_entry(self, entry, channel_id: str) -> ChannelVideo:
        """
        Parse a single RSS feed entry.

        Args:
            entry: feedparser entry object
            channel_id: YouTube channel ID

        Returns:
            ChannelVideo object with video metadata
        """
        # Extract video ID from entry.id (format: yt:video:VIDEO_ID)
        video_id = entry.id.split(":")[-1] if hasattr(entry, "id") else None

        # Parse published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        # Extract description
        description = ""
        if hasattr(entry, "media_group") and entry.media_group:
            description = entry.media_group.get("media_description", "")
        elif hasattr(entry, "summary"):
            description = entry.summary

        # Extract thumbnail
        thumbnail_url = None
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            thumbnail_url = (
                entry.media_thumbnail[0].get("url") if entry.media_thumbnail else None
            )

        return ChannelVideo(
            video_id=video_id or "",
            title=entry.title if hasattr(entry, "title") else "",
            url=entry.link if hasattr(entry, "link") else "",
            channel_id=channel_id,
            published_at=published_at,
            description=description,
            thumbnail_url=thumbnail_url,
        )

    def get_transcript(
        self, video_id: str, languages: list[str] = None, return_model: bool = False
    ) -> str | VideoTranscript | None:
        """
        Fetch transcript for a video.

        WARNING: YouTube rate limits transcript requests. If fetching many transcripts:
        - Use small batches (--limit 10-20)
        - Add delays between batches
        - Consider using proxies for production (see docs/YOUTUBE_TRANSCRIPTS.md)

        Args:
            video_id: YouTube video ID
            languages: List of language codes to try in order (default: ['en'])
            return_model: If True, return VideoTranscript model; if False, return plain text

        Returns:
            Transcript text, VideoTranscript model, or None if not available

        Raises:
            No exceptions raised - all errors are caught and logged
            Returns None if transcript unavailable for any reason

        See Also:
            docs/YOUTUBE_TRANSCRIPTS.md for rate limiting and proxy configuration
        """
        if languages is None:
            languages = ["en"]

        try:
            # Create API instance with proxy support if configured
            if youtube_proxy.is_configured:
                from youtube_transcript_api.proxies import WebshareProxyConfig

                proxy_config = WebshareProxyConfig(
                    proxy_username=youtube_proxy.username,
                    proxy_password=youtube_proxy.password,
                )
                ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)
                logger.debug(f"Using Webshare proxy for transcript request: {video_id}")
            else:
                ytt_api = YouTubeTranscriptApi()

            fetched_transcript = ytt_api.fetch(video_id, languages=languages)

            # Format transcript using TextFormatter
            formatter = TextFormatter()
            full_text = formatter.format_transcript(fetched_transcript)

            logger.debug(
                f"Successfully fetched transcript for {video_id} ({len(full_text)} chars)"
            )

            if return_model:
                return VideoTranscript(
                    video_id=video_id,
                    transcript=full_text,
                    languages=languages,
                    has_transcript=True,
                )
            return full_text

        except TranscriptsDisabled:
            logger.info(f"Transcripts disabled for video {video_id}")
            return None
        except NoTranscriptFound:
            logger.info(
                f"No English transcript found for video {video_id} in languages: {languages}"
            )
            return None
        except VideoUnavailable:
            logger.warning(f"Video {video_id} is unavailable")
            return None
        except Exception as e:
            # Catch-all for unexpected errors (including RequestBlocked from rate limiting)
            error_msg = str(e)
            if (
                "YouTube is blocking requests" in error_msg
                or "RequestBlocked" in error_msg
            ):
                logger.error(
                    f"YouTube rate limit hit for {video_id}. "
                    "See docs/YOUTUBE_TRANSCRIPTS.md for solutions (proxies, rate limiting, etc.)"
                )
            else:
                logger.error(f"Error fetching transcript for {video_id}: {error_msg}")
            return None

    def get_transcript_with_timestamps(
        self, video_id: str, languages: list[str] = None, return_model: bool = False
    ) -> list[TranscriptSegment] | VideoTranscript | None:
        """
        Fetch transcript with timestamps for a video.

        Args:
            video_id: YouTube video ID
            languages: List of language codes to try in order (default: ['en'])
            return_model: If True, return VideoTranscript model; if False, return list of TranscriptSegment

        Returns:
            List of TranscriptSegment objects, VideoTranscript model, or None if not available
        """
        if languages is None:
            languages = ["en"]

        try:
            # Create API instance with proxy support if configured
            if youtube_proxy.is_configured:
                from youtube_transcript_api.proxies import WebshareProxyConfig

                proxy_config = WebshareProxyConfig(
                    proxy_username=youtube_proxy.username,
                    proxy_password=youtube_proxy.password,
                )
                ytt_api = YouTubeTranscriptApi(proxy_config=proxy_config)
                logger.debug(
                    f"Using Webshare proxy for timestamped transcript request: {video_id}"
                )
            else:
                ytt_api = YouTubeTranscriptApi()

            fetched_transcript = ytt_api.fetch(video_id, languages=languages)

            # Convert to raw data format (list of dicts)
            transcript_data = fetched_transcript.to_raw_data()

            # Convert to TranscriptSegment objects
            segments = [
                TranscriptSegment(
                    text=segment["text"],
                    start=segment["start"],
                    duration=segment["duration"],
                )
                for segment in transcript_data
            ]

            # Format full transcript text using TextFormatter
            formatter = TextFormatter()
            full_text = formatter.format_transcript(fetched_transcript)

            logger.debug(
                f"Successfully fetched timestamped transcript for {video_id} "
                f"({len(segments)} segments)"
            )

            if return_model:
                return VideoTranscript(
                    video_id=video_id,
                    transcript=full_text,
                    segments=segments,
                    languages=languages,
                    has_transcript=True,
                )
            return segments

        except TranscriptsDisabled:
            logger.info(f"Transcripts disabled for video {video_id}")
            return None
        except NoTranscriptFound:
            logger.info(
                f"No transcript found for video {video_id} in languages: {languages}"
            )
            return None
        except VideoUnavailable:
            logger.warning(f"Video {video_id} is unavailable")
            return None
        except Exception as e:
            logger.error(
                f"Error fetching timestamped transcript for {video_id}: {str(e)}"
            )
            return None

    def validate_source(self, source: str) -> bool:
        """
        Validate that a channel ID is valid.

        Args:
            source: YouTube channel ID

        Returns:
            True if valid (starts with UC and has correct length)
        """
        # YouTube channel IDs typically start with "UC" and are 24 characters long
        return isinstance(source, str) and source.startswith("UC") and len(source) == 24


if __name__ == "__main__":
    # Example usage - run from project root with: python -m app.scrapers.youtube_rss

    scraper = YouTubeRSSScraper(
        channel_ids=["UC_x5XG1OV2P6uZZ5FSM9Ttw"]
    )  # Google Developers channel
    videos = scraper.scrape(hours=72, include_transcripts=True)
    for video in videos:
        print(f"Title: {video.title}")
        print(f"URL: {video.url}")
        print(f"Published at: {video.published_at}")
        print(f"Has Transcript: {video.has_transcript}")
        print(
            f"Transcript: {video.transcript[:100]}..."
            if video.transcript
            else "No Transcript"
        )
        print("-" * 40)