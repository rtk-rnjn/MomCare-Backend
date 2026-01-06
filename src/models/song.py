from __future__ import annotations

from typing import TypedDict, TYPE_CHECKING

from bson import ObjectId

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class SongDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    uri: str
    image_uri: str | None

    title: str | None
    artist: str | None
    duration: float | None
