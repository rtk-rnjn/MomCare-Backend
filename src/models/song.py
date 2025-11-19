from __future__ import annotations

from typing import NotRequired, TypedDict

from bson import ObjectId


class SongDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    uri: str
    image_uri: str | None

    title: str | None
    artist: str | None
    duration: float | None
