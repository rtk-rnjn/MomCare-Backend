from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_serializer
from pytz import timezone

from .exercise import Exercise
from .myplan import MyPlan

__all__ = ("User", "UserMedical", "History", "MoodHistory")


class MoodHistory(BaseModel):
    date: datetime = Field(default_factory=lambda: datetime.now(timezone("Asia/Kolkata")))
    mood: str


class History(BaseModel):
    date: datetime = Field(default_factory=lambda: datetime.now(timezone("Asia/Kolkata")))
    plan: Optional[MyPlan] = None
    exercises: List[Exercise] = []
    moods: List[MoodHistory] = []

    @field_serializer("date")
    def serialize_created_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone("Asia/Kolkata")))
    last_login: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class UserMedical(BaseModel):
    date_of_birth: datetime
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date: Optional[datetime] = None
    pre_existing_conditions: List[str] = []
    food_intolerances: List[str] = []
    dietary_preferences: List[str] = []

    @field_serializer("date_of_birth")
    def serialize_created_at(self, value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    @field_serializer("due_date")
    def serialize_due_date(self, value: Optional[datetime]) -> Optional[str]:
        if value:
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")
        return None
