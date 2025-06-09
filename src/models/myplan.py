from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field
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

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone("Asia/Kolkata")))

    def is_empty(self) -> bool:
        return not any([self.breakfast, self.lunch, self.dinner, self.snacks])

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )
