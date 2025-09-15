from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = ("FoodItem",)


class FoodItem(BaseModel):
    """
    Represents a food item with detailed nutritional information for maternal health tracking.

    Contains comprehensive nutritional data, allergen information, and consumption tracking
    to support healthy eating during pregnancy and postpartum recovery.
    """

    name: str = Field(
        ..., title="Food Name", description="Name of the food item", examples=["Grilled Salmon", "Spinach Salad", "Greek Yogurt"]
    )

    calories: Optional[float] = Field(None, description="Calories per serving", examples=[250.5], ge=0)
    protein: Optional[float] = Field(None, description="Protein content in grams", examples=[22.0], ge=0)
    carbs: Optional[float] = Field(None, description="Carbohydrate content in grams", examples=[15.5], ge=0)
    fat: Optional[float] = Field(None, description="Fat content in grams", examples=[12.3], ge=0)
    sodium: Optional[float] = Field(None, description="Sodium content in milligrams", examples=[450.0], ge=0)
    sugar: Optional[float] = Field(None, description="Sugar content in grams", examples=[8.2], ge=0)
    vitamin_contents: List[str] = Field(
        default_factory=list, description="List of vitamins present", examples=[["Vitamin D", "Vitamin B12", "Omega-3", "Folate"]]
    )
    allergic_ingredients: List[str] = Field(
        default_factory=list, description="List of potential allergens", examples=[["fish", "dairy", "nuts"]]
    )

    image_uri: Optional[str] = Field(default="", description="URL to food item image", examples=["https://example.com/salmon.jpg"])
    type: Optional[str] = Field(None, description="Food category", examples=["Protein", "Vegetable", "Dairy", "Grain"])

    consumed: Optional[bool] = Field(default=False, description="Whether this food item has been consumed")
    quantity: Optional[float] = Field(None, description="Quantity consumed (in grams or standard serving)", examples=[150.0], ge=0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Grilled Salmon",
                "calories": 250.5,
                "protein": 22.0,
                "carbs": 0.0,
                "fat": 12.3,
                "sodium": 450.0,
                "sugar": 0.0,
                "vitamin_contents": ["Vitamin D", "Vitamin B12", "Omega-3"],
                "allergic_ingredients": ["fish"],
                "image_uri": "https://example.com/grilled-salmon.jpg",
                "type": "Protein",
                "consumed": False,
                "quantity": 150.0,
            }
        }
    )
