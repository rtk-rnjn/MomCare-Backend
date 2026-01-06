from __future__ import annotations

from typing import TypedDict, TYPE_CHECKING

from bson import ObjectId

if TYPE_CHECKING:
    from typing_extensions import NotRequired


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
