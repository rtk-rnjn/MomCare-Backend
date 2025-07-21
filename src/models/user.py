from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pytz import timezone

from .exercise import Exercise
from .myplan import MyPlan

__all__ = ("User", "UserMedical", "History", "MoodHistory")


class MoodHistory(BaseModel):
    date: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")))
    mood: str

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )


class History(BaseModel):
    date: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")))
    plan: Optional[MyPlan] = None
    exercises: List[Exercise] = []
    moods: List[MoodHistory] = []

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )

    def is_empty(self) -> bool:
        return not (self.plan or self.exercises or self.moods)


class User(BaseModel):
    id: str
    first_name: str
    last_name: Optional[str] = None
    email_address: EmailStr
    password: str

    country_code: str = "91"
    country: str = "India"

    phone_number: str = ""

    medical_data: Optional[UserMedical] = None

    mood_history: List[MoodHistory] = []
    exercises: List[Exercise] = []
    plan: Optional[MyPlan] = MyPlan()

    history: List[History] = []

    # Server stuff
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")))
    last_login: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )


class UserMedical(BaseModel):
    date_of_birth: datetime
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date: Optional[datetime] = None
    pre_existing_conditions: List[str] = []
    food_intolerances: List[str] = []
    dietary_preferences: List[str] = []

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
