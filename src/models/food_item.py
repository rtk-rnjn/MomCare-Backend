from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

__all__ = ("FoodItem",)


class FoodItem(BaseModel):
    name: str = Field(..., title="Name", description="Name of the food item")

    calories: Optional[float] = Field(
        0, ge=0, title="Calories", description="Calories in the food item"
    )
    protein: Optional[float] = Field(
        0, ge=0, title="Protein", description="Protein content in the food item"
    )
    carbs: Optional[float] = Field(
        0, ge=0, title="Carbohydrates", description="Carbohydrates in the food item"
    )
    fat: Optional[float] = Field(
        0, ge=0, title="Fat", description="Fat content in the food item"
    )
    sodium: Optional[float] = Field(
        0, ge=0, title="Sodium", description="Sodium content in the food item"
    )
    sugar: Optional[float] = Field(
        0, ge=0, title="Sugar", description="Sugar content in the food item"
    )
    vitamin_contents: List[str] = Field(
        default_factory=list,
        title="Vitamin Content",
        description="Vitamin content in the food item",
    )
    allergic_ingredients: List[str] = Field(
        default_factory=list,
        title="Allergic Ingredients",
        description="Allergic ingredients in the food item",
    )

    image_name: Optional[str] = Field(
        None,
        title="Image Name",
        description="Filename or URL of the image of the food item",
    )

    type: Optional[str] = Field(None, title="Type", description="Type of the food item")

    consumed: Optional[bool] = Field(
        False, title="Consumed", description="Whether the food item has been consumed"
    )
