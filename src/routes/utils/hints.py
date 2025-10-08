from __future__ import annotations

from typing import Literal

UserField = Literal[
    "email_address",
    "first_name",
    "last_name",
    "password",
    "country_code",
    "country",
    "phone_number",
    "is_verified",
    "medical_data.date_of_birth",
    "medical_data.height",
    "medical_data.pre_pregnancy_weight",
    "medical_data.current_weight",
    "medical_data.due_date",
]

ArrayField = Literal[
    "medical_data.pre_existing_conditions",
    "medical_data.food_intolerances",
    "medical_data.dietary_preferences",
]

FieldType = UserField | ArrayField
