from __future__ import annotations

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field
from pytz import timezone

from .food_item import FoodItem

__all__ = ("MyPlan",)


class MyPlan(BaseModel):
    """
    Represents a comprehensive daily nutrition plan for maternal wellness.

    Organizes meals throughout the day with detailed nutritional tracking
    to support healthy eating during pregnancy and postpartum recovery.
    """

    breakfast: List[FoodItem] = Field(
        default_factory=list, description="Morning meal food items", examples=[[{"name": "Oatmeal with Berries", "calories": 250}]]
    )
    lunch: List[FoodItem] = Field(
        default_factory=list, description="Midday meal food items", examples=[[{"name": "Quinoa Salad", "calories": 350}]]
    )
    dinner: List[FoodItem] = Field(
        default_factory=list,
        description="Evening meal food items",
        examples=[[{"name": "Grilled Chicken with Vegetables", "calories": 400}]],
    )
    snacks: List[FoodItem] = Field(
        default_factory=list, description="Snack food items throughout the day", examples=[[{"name": "Greek Yogurt", "calories": 120}]]
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone("UTC")), description="When this meal plan was created")

    def is_empty(self) -> bool:
        """Check if the meal plan has any food items."""
        return not any([self.breakfast, self.lunch, self.dinner, self.snacks])

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "breakfast": [
                    {
                        "name": "Oatmeal with Berries",
                        "calories": 250.0,
                        "protein": 8.0,
                        "carbs": 45.0,
                        "fat": 4.0,
                        "vitamin_contents": ["Folate", "Iron"],
                        "type": "Grain",
                    },
                    {
                        "name": "Fresh Orange Juice",
                        "calories": 80.0,
                        "carbs": 20.0,
                        "vitamin_contents": ["Vitamin C"],
                        "type": "Beverage",
                    },
                ],
                "lunch": [
                    {
                        "name": "Quinoa Salad with Vegetables",
                        "calories": 350.0,
                        "protein": 12.0,
                        "carbs": 55.0,
                        "fat": 8.0,
                        "vitamin_contents": ["Folate", "Magnesium"],
                        "type": "Grain",
                    }
                ],
                "dinner": [
                    {
                        "name": "Grilled Salmon",
                        "calories": 250.0,
                        "protein": 22.0,
                        "fat": 12.0,
                        "vitamin_contents": ["Omega-3", "Vitamin D"],
                        "allergic_ingredients": ["fish"],
                        "type": "Protein",
                    },
                    {
                        "name": "Steamed Broccoli",
                        "calories": 50.0,
                        "protein": 3.0,
                        "carbs": 8.0,
                        "vitamin_contents": ["Vitamin C", "Folate"],
                        "type": "Vegetable",
                    },
                ],
                "snacks": [
                    {
                        "name": "Greek Yogurt",
                        "calories": 120.0,
                        "protein": 15.0,
                        "carbs": 8.0,
                        "fat": 3.0,
                        "vitamin_contents": ["Calcium", "Probiotics"],
                        "allergic_ingredients": ["dairy"],
                        "type": "Dairy",
                    }
                ],
                "created_at": "2024-01-15T00:00:00Z",
            }
        },
    )

    def is_old(self) -> bool:
        """
        Check if the plan is older than a day (crossed midnight).

        Returns:
            bool: True if the plan was created more than a day ago
        """
        now = datetime.now(timezone("UTC"))
        created_at = self.created_at.replace(tzinfo=timezone("UTC"))
        return (now - created_at).days > 0
