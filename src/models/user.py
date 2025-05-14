from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from .enums import (
    Country,
    DietaryPreference,
    Intolerance,
    MoodType,
    PreExistingCondition,
)
from .exercise import Exercise
from .myplan import MyPlan

__all__ = ("User", "UserMedical", "History", "MoodHistory")


class MoodHistory(BaseModel):
    date: datetime = datetime.now(timezone.utc)
    mood: MoodType


class History(BaseModel):
    date: datetime = datetime.now(timezone.utc)
    plan: Optional[MyPlan] = None
    exercise: List[Exercise] = []
    moods: List[MoodHistory] = []


class User(BaseModel):
    id: str
    first_name: str
    last_name: Optional[str] = None
    email_address: EmailStr
    password: str

    country_code: str = "91"
    country: Country = Country.INDIA

    phone_number: str = ""

    medical_data: Optional[UserMedical] = None

    mood_history: List[MoodHistory] = []
    exercises: List[Exercise] = []
    plan: MyPlan = MyPlan()

    history: List[History] = []

    # Server stuff
    created_at: datetime = datetime.now(timezone.utc)
    last_login: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False


class UserMedical(BaseModel):
    date_of_birth: datetime
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date: Optional[datetime] = None
    pre_existing_conditions: List[PreExistingCondition] = []
    food_intolerances: List[Intolerance] = []
    dietary_preferences: List[DietaryPreference] = []
