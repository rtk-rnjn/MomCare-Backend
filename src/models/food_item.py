from __future__ import annotations

from typing import TypedDict, TYPE_CHECKING

from bson import ObjectId

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class FoodItemDict(TypedDict, total=False):
    _id: NotRequired[ObjectId]

    name: str
    calories: float | None
    protein: float | None
    carbs: float | None
    fat: float | None
    sodium: float | None
    sugar: float | None
    vitamin_contents: list[str]
    allergic_ingredients: list[str]
    image_uri: str | None
    type: str | None
    consumed: bool | None
    quantity: float | None
