from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .food_item import FoodItem

__all__ = ("MyPlan",)


class MyPlan(BaseModel):
    """
    Represents a user's nutrition and hydration tracking plan.
    """

    breakfast: List[FoodItem] = Field(
        default_factory=list, title="Breakfast", description="List of breakfast items"
    )
    lunch: List[FoodItem] = Field(
        default_factory=list, title="Lunch", description="List of lunch items"
    )
    dinner: List[FoodItem] = Field(
        default_factory=list, title="Dinner", description="List of dinner items"
    )
    snacks: List[FoodItem] = Field(
        default_factory=list, title="Snacks", description="List of snack items"
    )