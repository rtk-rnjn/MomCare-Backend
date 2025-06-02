from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field
from pytz import timezone

__all__ = ("Exercise",)


class Exercise(BaseModel):
    """
    Represents an exercise with its type, duration, difficulty level, and progress tracking.
    """

    name: str
    exercise_type: str = "Yoga"
    duration: float
    description: str = ""
    tags: List[str] = []

    level: str = "Beginner"

    duration_completed: float

    assigned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone("Asia/Kolkata")),
    )
