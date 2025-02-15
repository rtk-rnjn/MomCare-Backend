from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from .enums import (
    Country,
    DietaryPreference,
    Intolerance,
    MoodType,
    PreExistingCondition,
)
from .exercise import Exercise
from .myplan import MyPlan

__all__ = ("User", "UserMedical", "History")


class History(BaseModel):
    date: datetime = Field(
        default_factory=datetime.utcnow, title="Date", description="Date of record"
    )
    plan: Optional["MyPlan"] = Field(
        None, title="Plan", description="User's assigned plan"
    )
    exercise: List[Exercise] = Field(
        default_factory=list,
        title="Exercises",
        description="List of completed exercises",
    )


class User(BaseModel):
    id: str = Field(
        ..., title="User ID", description="Unique identifier for the user", alias="_id"
    )
    first_name: str = Field(..., title="First Name", description="User's first name")
    last_name: Optional[str] = Field(
        None, title="Last Name", description="User's last name (surname). Optional."
    )
    email_address: EmailStr = Field(
        ..., title="Email Address", description="User's email address"
    )
    password: str = Field(
        ..., title="Password (Hashed)", description="User's hashed password"
    )

    country_code: str = Field(default="+91", title="Country Code")
    country: Country = Field(default=Country.INDIA, title="Country")

    phone_number: str = Field(
        ..., title="Phone Number", description="Phone number without country code"
    )

    medical_data: Optional[UserMedical] = Field(None, title="Medical Data")
    mood: Optional[MoodType] = Field(None, title="Mood")

    exercises: List[Exercise] = Field(default_factory=list, title="Active Exercises")
    plan: Optional["MyPlan"] = Field(None, title="Current Plan")
    history: List[History] = Field(default_factory=list, title="Exercise History")

    created_at: datetime = Field(
        default_factory=datetime.utcnow, title="Account Creation Date"
    )
    updated_at: Optional[datetime] = Field(None, title="Last Update Date")


class UserMedical(BaseModel):
    date_of_birth: datetime = Field(..., title="Date of Birth")
    height: float = Field(..., gt=0, title="Height (cm)")
    pre_pregnancy_weight: float = Field(..., gt=0, title="Pre-pregnancy Weight (kg)")
    current_weight: float = Field(..., gt=0, title="Current Weight (kg)")
    due_date: Optional[datetime] = Field(..., title="Due Date")
    pre_existing_conditions: List[PreExistingCondition] = Field(
        default_factory=list, title="Pre-existing Conditions"
    )
    food_intolerances: List[Intolerance] = Field(
        default_factory=list, title="Food Intolerances"
    )
    dietary_preferences: List[DietaryPreference] = Field(
        default_factory=list, title="Dietary Preferences"
    )
