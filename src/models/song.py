from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, Field


class SongMetadata(TypedDict, total=False):
    author: str | None
    title: str | None
    duration: float | None


class Song(TypedDict):
    _id: str

    mood: str
    playlist: str
    song_name: str
    image_name: str
    metadata: SongMetadata | None

    playlist_image_uri: str | None
    song_image_uri: str | None


class SongMetadataModel(BaseModel):
    author: str | None = None
    title: str | None = None
    duration: float | None = None

    class Config:
        extra = "ignore"


class SongModel(BaseModel):
    id: str = Field(..., alias="_id")

    mood: str
    playlist: str
    song_name: str
    image_name: str
    metadata: SongMetadataModel | None = None

    playlist_image_uri: str | None = None
    song_image_uri: str | None = None

    class Config:
        extra = "ignore"
