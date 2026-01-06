from __future__ import annotations

from typing import TypedDict, TYPE_CHECKING

from bson import ObjectId

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class MoodDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    user_id: str
    mood: str

    recorded_at_timestamp: float
