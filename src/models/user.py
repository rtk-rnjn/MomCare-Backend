from __future__ import annotations

from typing import NotRequired, TypedDict

from bson import ObjectId


class UserDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    id: str
    email_address: str
    password: str
    first_name: str
    last_name: NotRequired[str | None]
    country_code: NotRequired[str]

    country: NotRequired[str]
    phone_number: NotRequired[str]

    date_of_birth_timestamp: float
    height: float
    pre_pregnancy_weight: float
    current_weight: float
    due_date_timestamp: float

    pre_existing_conditions: list[str]
    food_intolerances: list[str]
    dietary_preferences: list[str]

    created_at_timestamp: float
    is_verified: bool
