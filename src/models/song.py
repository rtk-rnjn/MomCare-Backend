from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ("Song", "SongMetadata")


class SongMetadata(BaseModel):
    """
    Metadata information for audio content.

    Contains descriptive information about songs, music, or audio content
    used for relaxation and wellness during pregnancy and postpartum.
    """

    title: str | None = Field(None, description="Song or audio title", examples=["Peaceful Pregnancy Meditation"])
    artist: str | None = Field(None, description="Artist or creator name", examples=["Wellness Studio"])
    duration: float | None = Field(None, description="Duration in seconds", examples=[300.0], gt=0)

    model_config = ConfigDict(
        json_schema_extra={"example": {"title": "Peaceful Pregnancy Meditation", "artist": "Wellness Studio", "duration": 300.0}}
    )


class Song(BaseModel):
    """
    Represents an audio content item for maternal wellness.

    Includes meditation tracks, relaxing music, and wellness audio content
    designed to support mental health during pregnancy and postpartum.
    """

    uri: str = Field(..., description="Direct link to the audio file", examples=["https://example.com/meditation-track.mp3"])
    image_uri: str | None = Field(None, description="Cover image or thumbnail URL", examples=["https://example.com/cover-image.jpg"])
    metadata: SongMetadata | None = Field(None, description="Additional information about the audio content")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "uri": "https://example.com/prenatal-meditation.mp3",
                "image_uri": "https://example.com/meditation-cover.jpg",
                "metadata": {"title": "Prenatal Relaxation", "artist": "Mindful Motherhood", "duration": 900.0},
            }
        }
    )
