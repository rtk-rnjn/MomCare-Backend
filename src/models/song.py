from __future__ import annotations

from pydantic import BaseModel
from typing import Optional
class Song(BaseModel):
    uri: str
    image_uri: Optional[str] = None
    metadata: Optional[SongMetadata] = None


class SongMetadata(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    duration: Optional[float] = None
