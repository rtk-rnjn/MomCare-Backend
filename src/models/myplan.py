from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel
from pytz import timezone

from .food_item import FoodItem

__all__ = ("MyPlan",)


class MyPlan(BaseModel):
    """
    Represents a user's nutrition and hydration tracking plan.
    """

    breakfast: List[FoodItem] = []
    lunch: List[FoodItem] = []
    dinner: List[FoodItem] = []
    snacks: List[FoodItem] = []

    created_at: datetime = datetime.now(timezone("Asia/Kolkata"))

    class Config:
        json_encoders = {
            datetime: lambda datetime_object: datetime_object.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
