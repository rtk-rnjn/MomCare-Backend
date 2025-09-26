from __future__ import annotations

from datetime import datetime
from typing import List, NotRequired, Optional, TypedDict

from bson import ObjectId

__all__ = [
    "UserDict",
    "UserMedicalDict",
    "ExerciseDict",
    "FoodItemDict",
    "MyPlanDict",
    "HistoryDict",
    "MoodHistoryDict",
]


class MoodHistoryDict(TypedDict):
    date: datetime
    mood: str


class HistoryDict(TypedDict):
    date: datetime
    plan: Optional[MyPlanDict]
    exercises: List[ExerciseDict]
    moods: List[MoodHistoryDict]


class UserMedicalDict(TypedDict):
    date_of_birth: datetime
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date: Optional[datetime]
    pre_existing_conditions: List[str]
    food_intolerances: List[str]
    dietary_preferences: List[str]


class ExerciseDict(TypedDict):
    name: str
    exercise_type: str
    image_uri: Optional[str]
    duration: Optional[float]
    description: str
    tags: List[str]
    level: str
    week: str
    targeted_body_parts: List[str]
    duration_completed: float
    assigned_at: datetime


class FoodItemDict(TypedDict):
    name: str
    calories: Optional[float]
    protein: Optional[float]
    carbs: Optional[float]
    fat: Optional[float]
    sodium: Optional[float]
    sugar: Optional[float]
    vitamin_contents: List[str]
    allergic_ingredients: List[str]
    image_uri: Optional[str]
    type: Optional[str]
    consumed: Optional[bool]
    quantity: Optional[float]


class MyPlanDict(TypedDict):
    breakfast: List[FoodItemDict]
    lunch: List[FoodItemDict]
    dinner: List[FoodItemDict]
    snacks: List[FoodItemDict]
    created_at: datetime


class UserDict(TypedDict):
    _id: NotRequired[str]
    id: str
    first_name: str
    last_name: str
    email_address: str
    password: str

    country_code: str
    country: str

    phone_number: str
    medical_data: Optional[UserMedicalDict]
    exercises: List[ExerciseDict]
    plan: Optional[MyPlanDict]

    history: List[HistoryDict]
    created_at: datetime
    last_login: Optional[datetime]
    updated_at: Optional[datetime]
    last_login_ip: Optional[str]
    is_active: bool
    is_verified: bool


class SongMetadataDict(TypedDict):
    _id: NotRequired[ObjectId]
    title: Optional[str]
    artist: Optional[str]
    duration: Optional[float]
