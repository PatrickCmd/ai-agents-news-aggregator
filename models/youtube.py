"""Pydantic models for YouTube data structures."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class TranscriptSegment(BaseModel):
    """A single segment of a timestamped transcript."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "text": "Hello world",
                "start": 0.0,
                "duration": 1.5,
            }
        }
    )

    text: str = Field(..., description="The text content of this segment")
    start: float = Field(..., ge=0, description="Start time in seconds")
    duration: float = Field(..., ge=0, description="Duration in seconds")


class VideoTranscript(BaseModel):
    """YouTube video transcript data."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "transcript": "Never gonna give you up...",
                "segments": [
                    {"text": "Never gonna give you up", "start": 0.0, "duration": 2.5}
                ],
                "languages": ["en"],
                "has_transcript": True,
            }
        }
    )

    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    transcript: Optional[str] = Field(None, description="Full transcript text")
    segments: Optional[list[TranscriptSegment]] = Field(
        None, description="Timestamped transcript segments"
    )
    languages: list[str] = Field(
        default_factory=lambda: ["en"], description="Languages attempted for fetching"
    )
    has_transcript: bool = Field(
        default=False, description="Whether a transcript was successfully fetched"
    )


class ChannelVideo(BaseModel):
    """YouTube video metadata from channel RSS feed."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "dQw4w9WgXcQ",
                "title": "Rick Astley - Never Gonna Give You Up",
                "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
                "published_at": "2009-10-25T06:57:33Z",
                "description": "The official video for Never Gonna Give You Up",
                "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
                "transcript": "Never gonna give you up...",
                "has_transcript": True,
            }
        }
    )

    video_id: str = Field(..., min_length=1, description="YouTube video ID")
    title: str = Field(..., description="Video title")
    url: HttpUrl = Field(..., description="Video URL")
    channel_id: str = Field(..., min_length=1, description="YouTube channel ID")
    published_at: Optional[datetime] = Field(None, description="Publication timestamp")
    description: str = Field(default="", description="Video description")
    thumbnail_url: Optional[HttpUrl] = Field(None, description="Thumbnail image URL")
    transcript: Optional[str] = Field(
        None, description="Full transcript text if fetched"
    )
    has_transcript: Optional[bool] = Field(
        None, description="Whether transcript is available"
    )


class ChannelInfo(BaseModel):
    """YouTube channel information."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
                "name": "Rick Astley",
                "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            }
        }
    )

    channel_id: str = Field(
        ..., min_length=24, max_length=24, description="YouTube channel ID"
    )
    name: Optional[str] = Field(None, description="Channel name")
    url: Optional[HttpUrl] = Field(None, description="Channel URL")