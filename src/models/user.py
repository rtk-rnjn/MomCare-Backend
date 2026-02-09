from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal, NotRequired, TypedDict

from pydantic import BaseModel, EmailStr, Field

from .food_item import Allergen, FoodType


class AuthenticationProvider(str, Enum):
    INTERNAL = "internal"
    GOOGLE = "google"
    APPLE = "apple"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    LOCKED = "locked"
    DELETED = "deleted"


EMAIL_PROVIDER = Literal[
    "Apple",
    "Fastmail",
    "Google",
    "Microsoft",
    "ProtonMail",
    "Rackspace",
    "Yahoo",
    "Yandex",
    "Zoho",
]


class PasswordAlgorithm(str, Enum):
    BCRYPT = "bcrypt"


class CredentialsDict(TypedDict, total=False):
    _id: NotRequired[str]

    email_address: NotRequired[str | None]
    email_address_normalized: NotRequired[str | None]
    email_address_provider: NotRequired[EMAIL_PROVIDER | str | None]

    password_hash: NotRequired[str | None]
    password_algo: NotRequired[PasswordAlgorithm | None]

    google_id: str | None
    apple_id: str | None

    authentication_providers: set[AuthenticationProvider]

    created_at_timestamp: NotRequired[float]
    updated_at_timestamp: NotRequired[float]

    failed_login_attempts: NotRequired[int]
    failed_login_attempts_timestamp: NotRequired[float]
    locked_until_timestamp: NotRequired[float]

    is_internal: NotRequired[bool]
    account_status: NotRequired[AccountStatus]

    last_login_timestamp: NotRequired[float]

    verified_email: NotRequired[bool]
    verified_email_at_timestamp: NotRequired[float]


class CredentialsModel(BaseModel):
    email_address: EmailStr = Field(
        alias="email_address",
        description="The user's email address.",
        examples=["user@example.com"],
        title="Email Address",
    )
    password: str = Field(
        description="The user's password. Required if not using Google or Apple login.",
        examples=["strongpassword123"],
        title="Password",
    )

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

    food_intolerances: list[Allergen]
    dietary_preferences: list[FoodType]


class UserModel(BaseModel):
    id: str = Field(
        alias="_id",
        default_factory=lambda: str(uuid.uuid4()),
        description="The unique identifier for the user.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="User ID",
    )

    first_name: str | None = Field(
        default=None,
        description="The user's first name.",
        examples=["Ritik"],
        title="First Name",
    )
    last_name: str | None = Field(
        default=None,
        description="The user's last name.",
        examples=["Ranjan"],
        title="Last Name",
    )
    phone_number: str | None = Field(
        default=None,
        description="The user's phone number.",
        examples=["+919119119110"],
        title="Phone Number",
    )

    date_of_birth_timestamp: float | None = Field(
        default=None,
        description="The user's date of birth as a Unix timestamp.",
        examples=[946684800.0],
        title="Date of Birth",
    )
    height: float | None = Field(
        default=None,
        description="The user's height in centimeters.",
        examples=[165.0],
        title="Height",
    )
    pre_pregnancy_weight: float | None = Field(
        default=None,
        description="The user's pre-pregnancy weight in kilograms.",
        examples=[60.0],
        title="Pre-Pregnancy Weight",
    )
    current_weight: float | None = Field(
        default=None,
        description="The user's current weight in kilograms.",
        examples=[65.0],
        title="Current Weight",
    )
    due_date_timestamp: float | None = Field(
        default=None,
        description="The user's due date as a Unix timestamp.",
        examples=[1704067200.0],
        title="Due Date",
    )

    food_intolerances: list[Allergen] = Field(
        default_factory=list,
        description="A list of the user's food intolerances.",
        examples=[[Allergen.GLUTEN, Allergen.BANANA]],
        title="Food Intolerances",
    )
    dietary_preferences: list[FoodType] = Field(
        default_factory=list,
        description="A list of the user's dietary preferences.",
        examples=[[FoodType.VEG]],
        title="Dietary Preferences",
    )

    class Config:
        extra = "ignore"
