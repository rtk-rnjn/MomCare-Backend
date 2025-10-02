from __future__ import annotations

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

    calories: float | None = Field(None, description="Calories per serving", examples=[250.5], ge=0)
    protein: float | None = Field(None, description="Protein content in grams", examples=[22.0], ge=0)
    carbs: float | None = Field(None, description="Carbohydrate content in grams", examples=[15.5], ge=0)
    fat: float | None = Field(None, description="Fat content in grams", examples=[12.3], ge=0)
    sodium: float | None = Field(None, description="Sodium content in milligrams", examples=[450.0], ge=0)
    sugar: float | None = Field(None, description="Sugar content in grams", examples=[8.2], ge=0)
    vitamin_contents: list[str] = Field(
        default_factory=list, description="list of vitamins present", examples=[["Vitamin D", "Vitamin B12", "Omega-3", "Folate"]]
    )
    allergic_ingredients: list[str] = Field(
        default_factory=list, description="list of potential allergens", examples=[["fish", "dairy", "nuts"]]
    )

    image_uri: str | None = Field(default="", description="URL to food item image", examples=["https://example.com/salmon.jpg"])
    type: str | None = Field(None, description="Food category", examples=["Protein", "Vegetable", "Dairy", "Grain"])

    consumed: bool | None = Field(default=False, description="Whether this food item has been consumed")
    quantity: float | None = Field(None, description="Quantity consumed (in grams or standard serving)", examples=[150.0], ge=0)

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
