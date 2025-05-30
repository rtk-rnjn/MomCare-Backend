from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Song(BaseModel):
    uri: str
    image_uri: Optional[str] = None
    metadata: Optional[SongMetadata] = None


class SongMetadata(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    duration: Optional[float] = None
