from __future__ import annotations

from typing import List

from pydantic import BaseModel

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
