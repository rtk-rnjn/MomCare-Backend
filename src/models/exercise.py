from __future__ import annotations

import uuid
from typing import Literal, NotRequired, TypedDict

import arrow
from pydantic import BaseModel, Field


class ExerciseDict(TypedDict):
    _id: str

    name: str
    level: Literal["Advanced", "Beginner", "Intermediate"]
    description: str
    week: str
    tags: list[str]
    targeted_body_parts: list[str]
    image_name: str
    image_name_uri: str | None
    video_duration_seconds: float


class UserExerciseDict(TypedDict):
    _id: str

    user_id: str
    exercise_id: str
    added_at_timestamp: float
    video_duration_completed_seconds: NotRequired[float]


class ExerciseModel(BaseModel):
    id: str = Field(..., alias="_id")

    name: str
    level: Literal["Advanced", "Beginner", "Intermediate"]
    description: str
    week: str
    tags: list[str]
    targeted_body_parts: list[str]
    image_name: str
    image_name_uri: str | None = None
    video_duration_seconds: float

    class Config:
        extra = "ignore"


class UserExerciseModel(BaseModel):
    id: str = Field(alias="_id", default_factory=lambda: str(uuid.uuid4()))

    user_id: str
    exercise_id: str
    added_at_timestamp: float = Field(
        default_factory=lambda: arrow.now().float_timestamp
    )
    video_duration_completed_seconds: float | None = None

    class Config:
        extra = "ignore"
