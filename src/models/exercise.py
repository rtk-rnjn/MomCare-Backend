from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_serializer
from pytz import timezone

__all__ = ("Exercise",)


class Exercise(BaseModel):
    """
    Represents an exercise with its type, duration, difficulty level, and progress tracking.
    """

    name: str
    exercise_type: str = "Yoga"
    duration: Optional[float] = None
    description: str = ""
    tags: List[str] = []

    level: str = "Beginner"
    week: str

    targeted_body_parts: List[str] = []

    duration_completed: float = 0

    assigned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone("Asia/Kolkata")),
    )

    @field_serializer("assigned_at")
    def serialize_assigned_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
