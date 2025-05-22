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
    name: str
    exercise_type: ExerciseType = ExerciseType.YOGA
    duration: float
    description: str = ""
    tags: List[str] = []

    level: DifficultyType

    exercise_image_uri: str
    duration_completed: float
