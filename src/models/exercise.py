from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field
from pytz import timezone

__all__ = ("Exercise",)


class Exercise(BaseModel):
    """
    Represents a fitness exercise with tracking capabilities for maternal wellness.
    
    Includes exercise details, difficulty progression, and completion tracking
    tailored for pregnancy and postpartum fitness needs.
    """

    name: str = Field(..., description="Name of the exercise", examples=["Prenatal Yoga", "Walking", "Pelvic Floor Exercises"])
    exercise_type: str = Field(default="Yoga", description="Type/category of exercise", examples=["Yoga", "Cardio", "Strength", "Stretching"])
    image_uri: Optional[str] = Field(None, description="URL to exercise demonstration image", examples=["https://example.com/exercise-image.jpg"])
    duration: Optional[float] = Field(None, description="Recommended duration in minutes", examples=[30.0], gt=0, le=180)
    description: str = Field(default="", description="Detailed exercise description and instructions", examples=["Gentle yoga poses designed for prenatal wellness and relaxation"])
    tags: List[str] = Field(default_factory=list, description="Exercise tags for categorization", examples=[["prenatal", "relaxation", "flexibility"]])

    level: str = Field(default="Beginner", description="Difficulty level", examples=["Beginner", "Intermediate", "Advanced"])
    week: str = Field(..., description="Pregnancy week or postpartum week this exercise is suitable for", examples=["Week 12", "Week 20", "Postpartum Week 6"])

    targeted_body_parts: List[str] = Field(default_factory=list, description="Body parts targeted by this exercise", examples=[["core", "back", "legs", "pelvic floor"]])

    duration_completed: float = Field(default=0, description="Duration completed by user in minutes", examples=[25.0], ge=0)

    assigned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone("UTC")),
        description="When this exercise was assigned to the user"
    )

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "name": "Prenatal Yoga Flow",
                "exercise_type": "Yoga",
                "image_uri": "https://example.com/prenatal-yoga.jpg",
                "duration": 30.0,
                "description": "A gentle yoga sequence designed specifically for pregnant women to improve flexibility, reduce stress, and prepare the body for childbirth.",
                "tags": ["prenatal", "relaxation", "flexibility", "stress-relief"],
                "level": "Beginner",
                "week": "Week 20",
                "targeted_body_parts": ["core", "back", "hips", "shoulders"],
                "duration_completed": 25.0,
                "assigned_at": "2024-01-15T08:00:00Z"
            }
        }
    )
