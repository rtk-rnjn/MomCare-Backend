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
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        alias="_id",
        description="The unique identifier.",
        title="Exercise ID",
    )

    name: str = Field(..., description="The name of the exercise.", title="Exercise Name")
    level: Literal["Advanced", "Beginner", "Intermediate"] = Field(
        ...,
        description="The difficulty level of the exercise.",
        title="Exercise Level",
    )
    description: str = Field(..., description="A detailed description of the exercise.", title="Exercise Description")
    week: str = Field(..., description="The week of pregnancy for which the exercise is suitable.", title="Week of Pregnancy")
    tags: list[str] = Field(..., description="A list of tags associated with the exercise.", title="Exercise Tags")
    targeted_body_parts: list[str] = Field(
        ..., description="A list of body parts targeted by the exercise.", title="Targeted Body Parts"
    )
    image_name: str = Field(..., description="The name of the image file associated with the exercise.", title="Exercise Image Name")
    image_name_uri: str | None = Field(None, description="The URI of the image representing the exercise.", title="Exercise Image URI")
    video_duration_seconds: float = Field(
        ..., description="The duration of the exercise video in seconds.", title="Exercise Video Duration in Seconds"
    )

    class Config:
        extra = "ignore"


class UserExerciseModel(BaseModel):
    id: str = Field(
        alias="_id",
        default_factory=lambda: str(uuid.uuid4()),
        description="The unique identifier for the user exercise record.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="User Exercise ID",
    )

    user_id: str = Field(
        ..., description="The unique identifier of the user.", title="User ID", examples=["123e4567-e89b-12d3-a456-426614174000"]
    )
    exercise_id: str = Field(
        ...,
        description="The unique identifier of the exercise.",
        title="Exercise ID",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
    )
    added_at_timestamp: float = Field(
        default_factory=lambda: arrow.now().float_timestamp,
        description="The timestamp when the exercise was added to the user's plan.",
        title="Added At Timestamp",
        examples=[1622505600.0],
    )
    video_duration_completed_seconds: float | None = Field(
        None,
        description="The duration in seconds of the exercise video that the user has completed. Null if not started or not applicable.",
        title="Video Duration Completed in Seconds",
        examples=[120.0],
    )

    class Config:
        extra = "ignore"
