from __future__ import annotations

from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field

from .food_item import Allergen, FoodType


class CredentialsDict(TypedDict):
    _id: NotRequired[str]

    email_address: str
    password: str


class CredentialsModel(BaseModel):
    email_address: str
    password: str

    class Config:
        extra = "ignore"


class UserDict(TypedDict, total=False):
    _id: NotRequired[str]

    first_name: str
    last_name: str | None
    phone_number: str | None

    date_of_birth_timestamp: float
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date_timestamp: float

    pre_existing_conditions: list[str]
    food_intolerances: list[Allergen]
    dietary_preferences: list[FoodType]

    created_at_timestamp: NotRequired[float]
    last_login_timestamp: NotRequired[float]
    verified_email: NotRequired[bool]


class UserModel(BaseModel):
    id: str = Field(..., alias="_id")

    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None

    date_of_birth_timestamp: float | None = None
    height: float | None = None
    pre_pregnancy_weight: float | None = None
    current_weight: float | None = None
    due_date_timestamp: float | None = None

    pre_existing_conditions: list[str] = Field(default_factory=list)
    food_intolerances: list[Allergen] = Field(default_factory=list)
    dietary_preferences: list[FoodType] = Field(default_factory=list)

    class Config:
        extra = "ignore"
