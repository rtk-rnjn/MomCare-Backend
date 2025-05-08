from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

__all__ = ("FoodItem",)


class FoodItem(BaseModel):
    name: str = Field(..., title="Name", description="Name of the food item")

    calories: Optional[float] = None
    protein: Optional[float] = None
    carbs: Optional[float] = None
    fat: Optional[float] = None
    sodium: Optional[float] = None
    sugar: Optional[float] = None
    vitamin_contents: List[str] = []
    allergic_ingredients: List[str] = []

    image_name: Optional[str] = ""
    type: Optional[str] = None

    consumed: Optional[bool] = False
    quantity: Optional[float] = None
    consumed_at: Optional[str] = None
