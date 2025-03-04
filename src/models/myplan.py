from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .enums import MealType
from .food_item import FoodItem

__all__ = ("MyPlan",)


class MyPlan(BaseModel):
    """
    Represents a user's nutrition and hydration tracking plan.
    """

    current_water_intake: int = Field(
        0, ge=0, description="Current amount of water consumed (milliliters)."
    )

    meals: dict[MealType, list[FoodItem]] = Field(
        {}, description="Dictionary of meals with their food items."
    )
