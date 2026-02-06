from __future__ import annotations

from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class FoodReferenceDict(TypedDict):
    food_id: str
    consumed_at_timestamp: float | None
    count: int


class FoodReferenceModel(BaseModel):
    food_id: str
    consumed_at_timestamp: float | None
    count: int

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


class MyPlanModel(BaseModel):
    id: str = Field(..., alias="_id")

    user_id: str

    breakfast: list[FoodReferenceModel]
    lunch: list[FoodReferenceModel]
    dinner: list[FoodReferenceModel]
    snacks: list[FoodReferenceModel]

    created_at_timestamp: float | None = None

    class Config:
        extra = "ignore"
