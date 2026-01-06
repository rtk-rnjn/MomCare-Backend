from __future__ import annotations

from typing import TypedDict, TYPE_CHECKING

from bson import ObjectId

from .food_item import FoodItemDict

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class MyPlanDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    user_id: str

    breakfast: list[FoodItemDict]
    lunch: list[FoodItemDict]
    dinner: list[FoodItemDict]
    snacks: list[FoodItemDict]

    created_at_timestamp: float
