from __future__ import annotations

from enum import Enum


class MedicalField(str, Enum):
    PRE_EXISTING_CONDITIONS = "pre_existing_conditions"
    FOOD_INTOLERANCES = "food_intolerances"
    DIETARY_PREFERENCES = "dietary_preferences"


class RedisKeyManager:
    MedicalField = MedicalField

    def user_id(self, /, id: str) -> str:
        return f"user:{id}"

    def user_email_address(self, /, email_address: str) -> str:
        return f"user:email_address:{email_address}"

    def user_medical_data(self, /, id: str) -> str:
        return f"user:{id}:medical_data"

    def user_medical_data_field(self, /, id: str, field: MedicalField) -> str:
        return f"user:{id}:medical_data:{field.value}"

    def user_plan(self, /, id: str) -> str:
        return f"user:{id}:plan"

    def user_exercises(self, /, id: str) -> str:
        return f"user:{id}:exercises"

    def food_item(self, /, food_name: str) -> str:
        return f"food_item:{food_name}"

    def food_image(self, /, food_name: str) -> str:
        return f"food_image:{food_name}"

    def otp(self, /, email_address: str) -> str:
        return f"otp:{email_address}"

    def song_metadata(self, /, key: str) -> str:
        return f"song_metadata:{key}"
