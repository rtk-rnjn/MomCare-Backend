from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pytz import timezone

from .exercise import Exercise
from .myplan import MyPlan

__all__ = ("User", "UserMedical", "History", "MoodHistory", "PartialUser")


class MoodHistory(BaseModel):
    """Tracks user's mood at a specific date and time."""

    date: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")), description="Date and time when mood was recorded")
    mood: str = Field(..., description="User's mood", examples=["happy", "sad", "excited", "anxious", "calm"])

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={"example": {"date": "2024-01-15T10:30:00Z", "mood": "happy"}},
    )


class History(BaseModel):
    """Represents a day's worth of health and fitness activities."""

    date: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")), description="Date of the recorded activities")
    plan: MyPlan | None = Field(None, description="Nutrition plan for the day")
    exercises: list[Exercise] = Field(default_factory=list, description="Exercises completed during the day")
    moods: list[MoodHistory] = Field(default_factory=list, description="Mood entries for the day")

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "date": "2024-01-15T00:00:00Z",
                "plan": {
                    "breakfast": [{"name": "Oatmeal", "calories": 150}],
                    "lunch": [{"name": "Grilled Chicken Salad", "calories": 350}],
                    "dinner": [{"name": "Salmon with Vegetables", "calories": 400}],
                    "snacks": [{"name": "Apple", "calories": 80}],
                },
                "exercises": [{"name": "Morning Yoga", "exercise_type": "Yoga", "duration": 30.0, "level": "Beginner"}],
                "moods": [{"date": "2024-01-15T10:30:00Z", "mood": "energetic"}],
            }
        },
    )

    def is_empty(self) -> bool:
        return not (self.plan or self.exercises or self.moods)


class User(BaseModel):
    """
    Complete user profile model containing personal information, health data, and activity history.

    This model represents a registered user in the MomCare system with all their associated
    health tracking data, exercise history, and preferences.
    """

    id: str = Field(..., description="Unique user identifier", examples=["user_123456789"])
    first_name: str = Field(..., description="User's first name", examples=["Sarah"])
    last_name: str | None = Field(None, description="User's last name", examples=["Johnson"])
    email_address: EmailStr = Field(..., description="User's email address", examples=["sarah.johnson@example.com"])
    password: str = Field(..., description="User's encrypted password (hashed)")

    country_code: str = Field(default="91", description="Country code for phone number", examples=["91", "1", "44"])
    country: str = Field(default="India", description="User's country", examples=["India", "United States", "United Kingdom"])

    phone_number: str = Field(default="", description="User's phone number", examples=["+1234567890"])

    medical_data: UserMedical | None = Field(None, description="User's medical and health information")

    mood_history: list[MoodHistory] = Field(default_factory=list, description="Historical mood tracking data")
    exercises: list[Exercise] = Field(default_factory=list, description="User's current exercise list")
    plan: MyPlan | None = Field(default_factory=MyPlan, description="Current nutrition plan")

    history: list[History] = Field(default_factory=list, description="Historical daily activity records")

    # Server stuff
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")), description="Account creation timestamp")
    last_login: datetime | None = Field(None, description="Last login timestamp")
    updated_at: datetime | None = Field(None, description="Last profile update timestamp")
    last_login_ip: str | None = Field(None, description="IP address of last login", examples=["192.168.1.1"])
    is_active: bool = Field(default=True, description="Whether the account is active")
    is_verified: bool = Field(default=False, description="Whether the email is verified")

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "id": "user_123456789",
                "first_name": "Sarah",
                "last_name": "Johnson",
                "email_address": "sarah.johnson@example.com",
                "password": "hashed_password_here",
                "country_code": "1",
                "country": "United States",
                "phone_number": "+1234567890",
                "medical_data": {
                    "date_of_birth": "1990-05-15T00:00:00Z",
                    "height": 165.0,
                    "pre_pregnancy_weight": 65.0,
                    "current_weight": 70.0,
                    "due_date": "2024-06-15T00:00:00Z",
                    "pre_existing_conditions": ["hypertension"],
                    "food_intolerances": ["lactose"],
                    "dietary_preferences": ["vegetarian"],
                },
                "mood_history": [],
                "exercises": [],
                "plan": {"breakfast": [], "lunch": [], "dinner": [], "snacks": []},
                "history": [],
                "created_at": "2024-01-01T00:00:00Z",
                "last_login": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T09:00:00Z",
                "last_login_ip": "192.168.1.1",
                "is_active": True,
                "is_verified": True,
            }
        },
    )


class UserMedical(BaseModel):
    """
    Medical and health information for maternal wellness tracking.

    Contains essential health metrics and preferences for personalized care recommendations.
    """

    date_of_birth: datetime = Field(..., description="User's date of birth", examples=["1990-05-15T00:00:00Z"])
    height: float = Field(..., description="Height in centimeters", examples=[165.0], gt=0, le=300)
    pre_pregnancy_weight: float = Field(..., description="Weight before pregnancy in kilograms", examples=[65.0], gt=0, le=500)
    current_weight: float = Field(..., description="Current weight in kilograms", examples=[70.0], gt=0, le=500)
    due_date: datetime | None = Field(None, description="Expected due date (if pregnant)", examples=["2024-06-15T00:00:00Z"])
    pre_existing_conditions: list[str] = Field(
        default_factory=list, description="Known medical conditions", examples=[["diabetes", "hypertension"]]
    )
    food_intolerances: list[str] = Field(
        default_factory=list, description="Food allergies and intolerances", examples=[["lactose", "gluten", "nuts"]]
    )
    dietary_preferences: list[str] = Field(
        default_factory=list, description="Dietary choices and preferences", examples=[["vegetarian", "low-sodium", "organic"]]
    )

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "date_of_birth": "1990-05-15T00:00:00Z",
                "height": 165.0,
                "pre_pregnancy_weight": 65.0,
                "current_weight": 70.0,
                "due_date": "2024-06-15T00:00:00Z",
                "pre_existing_conditions": ["hypertension"],
                "food_intolerances": ["lactose"],
                "dietary_preferences": ["vegetarian", "low-sodium"],
            }
        },
    )


class PartialUser(BaseModel):
    """
    Partial user model for updates and modifications.

    Contains user information that can be updated without requiring all fields.
    """

    first_name: str = Field(..., description="User's first name", examples=["Sarah"])
    last_name: str | None = Field(None, description="User's last name", examples=["Johnson"])
    email_address: EmailStr = Field(..., description="User's email address", examples=["sarah.johnson@example.com"])

    country_code: str = Field(default="91", description="Country code for phone number", examples=["91", "1", "44"])
    country: str = Field(default="India", description="User's country", examples=["India", "United States", "United Kingdom"])

    phone_number: str = Field(default="", description="User's phone number", examples=["+1234567890"])

    medical_data: UserMedical | None = Field(None, description="User's medical and health information")

    mood_history: list[MoodHistory] = Field(default_factory=list, description="Historical mood tracking data")
    exercises: list[Exercise] = Field(default_factory=list, description="User's current exercise list")
    plan: MyPlan | None = Field(default_factory=MyPlan, description="Current nutrition plan")

    history: list[History] = Field(default_factory=list, description="Historical daily activity records")

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "first_name": "Sarah",
                "last_name": "Johnson",
                "email_address": "sarah.johnson@example.com",
                "country_code": "1",
                "country": "United States",
                "phone_number": "+1234567890",
                "medical_data": {
                    "date_of_birth": "1990-05-15T00:00:00Z",
                    "height": 165.0,
                    "pre_pregnancy_weight": 65.0,
                    "current_weight": 70.0,
                },
            }
        },
    )
