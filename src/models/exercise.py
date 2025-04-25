from __future__ import annotations

import datetime
from typing import List, Optional

from pydantic import BaseModel

from .enums import DifficultyType, ExerciseType

__all__ = ("Exercise",)


class Exercise(BaseModel):
    """
    Represents an exercise with its type, duration, difficulty level, and progress tracking.
    """

    exercise_type: ExerciseType
    duration: float
    description: str = ""
    tags: List[str] = []

    level: DifficultyType

    exercise_image_name: str

    duration_completed: float

    is_completed: bool = False
    completed_at: Optional[datetime.datetime] = None
