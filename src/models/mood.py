from __future__ import annotations

from typing import NotRequired, TypedDict

from bson import ObjectId


class MoodDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    user_id: str
    mood: str

    recorded_at_timestamp: float
