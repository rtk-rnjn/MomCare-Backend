from __future__ import annotations

from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class FoodReferenceDict(TypedDict):
    food_id: str
    consumed_at_timestamp: float | None
    count: int


class FoodReferenceModel(BaseModel):
    food_id: str
    consumed_at_timestamp: float | None = Field(
        None,
        description="The timestamp when the food was consumed. Null if not consumed yet.",
        title="Consumed At Timestamp",
    )
    count: int = Field(
        ...,
        description="The count of the food items.",
        title="Count",
    )

    class Config:
        extra = "ignore"


class MyPlanDict(TypedDict):
    _id: NotRequired[str]

    user_id: str

    breakfast: list[FoodReferenceDict]
    lunch: list[FoodReferenceDict]
    dinner: list[FoodReferenceDict]
    snacks: list[FoodReferenceDict]

    created_at_timestamp: NotRequired[float]

    original_breakfast: list[FoodReferenceDict]
    original_lunch: list[FoodReferenceDict]
    original_dinner: list[FoodReferenceDict]
    original_snacks: list[FoodReferenceDict]


class PartialMyPlanModel(BaseModel):
    breakfast: list[FoodReferenceModel] = Field(..., description="The list of food items for breakfast.", title="Breakfast")
    lunch: list[FoodReferenceModel] = Field(..., description="The list of food items for lunch.", title="Lunch")
    dinner: list[FoodReferenceModel] = Field(..., description="The list of food items for dinner.", title="Dinner")
    snacks: list[FoodReferenceModel] = Field(..., description="The list of food items for snacks.", title="Snacks")

    class Config:
        extra = "ignore"


class MyPlanModel(BaseModel):
    id: str = Field(
        ...,
        alias="_id",
        description="The unique identifier for the plan.",
        title="Plan ID",
    )

    user_id: str

    breakfast: list[FoodReferenceModel] = Field(..., description="The list of food items for breakfast.", title="Breakfast")
    lunch: list[FoodReferenceModel] = Field(..., description="The list of food items for lunch.", title="Lunch")
    dinner: list[FoodReferenceModel] = Field(..., description="The list of food items for dinner.", title="Dinner")
    snacks: list[FoodReferenceModel] = Field(..., description="The list of food items for snacks.", title="Snacks")

    created_at_timestamp: float | None = Field(
        None, description="The timestamp when the plan was created.", title="Created At Timestamp"
    )

    original_breakfast: list[FoodReferenceModel] = Field(
        ..., description="The original list of food items for breakfast.", title="Original Breakfast"
    )
    original_lunch: list[FoodReferenceModel] = Field(
        ..., description="The original list of food items for lunch.", title="Original Lunch"
    )
    original_dinner: list[FoodReferenceModel] = Field(
        ..., description="The original list of food items for dinner.", title="Original Dinner"
    )
    original_snacks: list[FoodReferenceModel] = Field(
        ..., description="The original list of food items for snacks.", title="Original Snacks"
    )

    class Config:
        extra = "ignore"
