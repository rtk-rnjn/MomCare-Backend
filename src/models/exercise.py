from __future__ import annotations

from typing import NotRequired, TypedDict

from bson import ObjectId


class ExerciseDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    user_id: str

    name: str
    exercise_type: str
    image_uri: str | None
    duration: float | None
    description: str
    tags: list[str]
    level: str
    week: str
    targeted_body_parts: list[str]

    duration_completed: float

    assigned_at_timestamp: float
