from __future__ import annotations

import uuid
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

MoodType = Literal["Happy", "Sad", "Stressed", "Angry"]


class SongMetadata(TypedDict, total=False):
    author: str | None
    title: str | None
    duration: float | None


class SongDict(TypedDict):
    _id: str

    mood: MoodType
    playlist: str
    song_name: str
    image_name: str
    metadata: SongMetadata | None

    playlist_image_uri: str | None
    song_image_uri: str | None


class SongMetadataModel(BaseModel):
    author: str | None = Field(None, description="The author of the song.", title="Author")
    title: str | None = Field(None, description="The title of the song.", title="Title")
    duration: float | None = Field(None, description="The duration of the song in seconds.", title="Duration")

    class Config:
        extra = "ignore"


class SongModel(BaseModel):
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="The unique identifier for the song.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Song ID",
    )

    mood: MoodType = Field(
        ..., description="The mood associated with the song.", examples=["Happy", "Sad", "Stressed", "Angry"], title="Mood"
    )
    playlist: str = Field(..., description="The playlist to which the song belongs.", title="Playlist")
    song_name: str = Field(..., description="The name of the song.", title="Song Name")
    image_name: str = Field(..., description="The name of the image file associated with the song.", title="Image Name")
    metadata: SongMetadataModel | None = Field(None, description="Metadata information about the song.", title="Metadata")

    playlist_image_uri: str | None = Field(None, description="The URI of the playlist image.", title="Playlist Image URI")
    song_image_uri: str | None = Field(None, description="The URI of the song image.", title="Song Image URI")

    class Config:
        extra = "ignore"
