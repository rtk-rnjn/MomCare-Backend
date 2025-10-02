from __future__ import annotations

from datetime import datetime
from typing import NotRequired, TypedDict

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
    plan: MyPlanDict | None
    exercises: list[ExerciseDict]
    moods: list[MoodHistoryDict]


class UserMedicalDict(TypedDict):
    date_of_birth: datetime
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date: datetime | None
    pre_existing_conditions: list[str]
    food_intolerances: list[str]
    dietary_preferences: list[str]


class ExerciseDict(TypedDict):
    name: str
    exercise_type: str
    image_uri: str | None
    duration: float | None
    description: str
    tags: list[str]
    level: str
    week: str
    targeted_body_parts: list[str]
    duration_completed: float
    assigned_at: datetime


class FoodItemDict(TypedDict):
    name: str
    calories: float | None
    protein: float | None
    carbs: float | None
    fat: float | None
    sodium: float | None
    sugar: float | None
    vitamin_contents: list[str]
    allergic_ingredients: list[str]
    image_uri: str | None
    type: str | None
    consumed: bool | None
    quantity: float | None


class MyPlanDict(TypedDict):
    breakfast: list[FoodItemDict]
    lunch: list[FoodItemDict]
    dinner: list[FoodItemDict]
    snacks: list[FoodItemDict]
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
    medical_data: UserMedicalDict | None
    exercises: list[ExerciseDict]
    plan: MyPlanDict | None

    history: list[HistoryDict]
    created_at: datetime
    last_login: datetime | None
    updated_at: datetime | None
    last_login_ip: str | None
    is_active: bool
    is_verified: bool


class SongMetadataDict(TypedDict):
    _id: NotRequired[ObjectId]
    title: str | None
    artist: str | None
    duration: float | None
