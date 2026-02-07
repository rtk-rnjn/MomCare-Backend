from __future__ import annotations

from typing import Literal

import arrow
from fastapi import APIRouter, Body, Depends, HTTPException, Path
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import MyPlanDict, UserExerciseDict
from src.routes.api.utils import get_user_id

router = APIRouter(prefix="/update", tags=["Update"])

database: Database = app.state.mongo_database
exercises_collection: Collection[UserExerciseDict] = database["exercises"]
plans_collection: Collection[MyPlanDict] = database["plans"]


Meal = Literal["breakfast", "lunch", "dinner", "snacks"]


def _plan_filter(plan_id: str, user_id: str) -> dict:
    return {"_id": plan_id, "user_id": user_id}


async def _update_consumed(plan_id: str, meal: Meal, food_id: str, user_id: str, value):
    result = await plans_collection.update_one(
        _plan_filter(plan_id, user_id),
        {"$set": {f"{meal}.$[food].consumed_at_timestamp": value}},
        array_filters=[{"food.food_id": food_id}],
    )
    return result.modified_count == 1


def _inc_food(plan_id: str, meal: Meal, food_id: str, user_id: str, delta: int):
    return plans_collection.update_one(
        {**_plan_filter(plan_id, user_id), f"{meal}.food_id": food_id},
        {"$inc": {f"{meal}.$.count": delta}},
    )


@router.post(
    "/exercise/{exercise_id}",
    name="Update Exercise Duration",
    status_code=200,
    response_model=bool,
    response_description="Whether the exercise duration was successfully updated.",
    summary="Update the duration of an exercise",
    description="Update the duration of an exercise the user has completed.",
    responses={
        200: {"description": "Exercise duration updated successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "Exercise not found."},
        422: {"description": "Validation error. Invalid exercise ID or duration."},
    },
)
async def update_exercise(
    exercise_id: str = Path(
        description="The ID of the exercise to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Exercise ID",
        alias="exercise_id",
    ),
    duration: float = Body(
        description="The duration of the exercise in seconds.",
        examples=[120.0],
        embed=True,
        gt=0,
        alias="duration",
        title="Exercise Duration",
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    update_result = await exercises_collection.update_one(
        {"_id": exercise_id, "user_id": user_id},
        {"$set": {"video_duration_completed_seconds": duration}},
    )
    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Exercise not found")

    return update_result.modified_count == 1


@router.post(
    "/myplan/{plan_id}/{meal}/{food_id}/consume",
    name="Consume Food Item",
    status_code=200,
    response_model=bool,
    response_description="Whether the food item was successfully marked as consumed.",
    summary="Mark a food item as consumed",
    description="Mark a specific food item in a meal plan as consumed at the current timestamp.",
    responses={
        200: {"description": "Food item marked as consumed successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "Plan or food item not found."},
        422: {"description": "Validation error. Invalid plan ID, meal, or food ID."},
    },
)
async def consume_food(
    plan_id: str = Path(
        description="The ID of the meal plan to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Plan ID",
        alias="plan_id",
    ),
    meal: Meal = Path(
        description="The meal in which the food item is located.",
        examples=["lunch"],
        title="Meal",
        alias="meal",
    ),
    food_id: str = Path(
        description="The ID of the food item to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food ID",
        alias="food_id",
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    return await _update_consumed(plan_id, meal, food_id, user_id, arrow.now().timestamp())


@router.post(
    "/myplan/{plan_id}/{meal}/{food_id}/unconsume",
    name="Unconsume Food Item",
    status_code=200,
    response_model=bool,
    response_description="Whether the food item was successfully marked as unconsumed.",
    summary="Mark a food item as unconsumed",
    description="Mark a specific food item in a meal plan as unconsumed.",
    responses={
        200: {"description": "Food item marked as unconsumed successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "Plan or food item not found."},
        422: {"description": "Validation error. Invalid plan ID, meal, or food ID."},
    },
)
async def unconsume_food(
    plan_id: str = Path(
        description="The ID of the meal plan to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Plan ID",
        alias="plan_id",
    ),
    meal: Meal = Path(
        description="The meal in which the food item is located.",
        examples=["lunch"],
        title="Meal",
        alias="meal",
    ),
    food_id: str = Path(
        description="The ID of the food item to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food ID",
        alias="food_id",
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    return await _update_consumed(plan_id, meal, food_id, user_id, None)


@router.post(
    "/myplan/{plan_id}/{meal}/add/{food_id}",
    name="Add Food Item to Meal",
    status_code=200,
    response_model=bool,
    response_description="Whether the food item was successfully added to the meal.",
    summary="Add a food item to a meal",
    description="Add a specific food item to a meal in the user's meal plan. If the food item already exists in the meal, its count will be incremented by 1.",
    responses={
        200: {"description": "Food item added to meal successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "Plan not found."},
        422: {"description": "Validation error. Invalid plan ID, meal, or food ID."},
    },
)
async def add_food_to_meal(
    plan_id: str = Path(
        description="The ID of the meal plan to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Plan ID",
        alias="plan_id",
    ),
    meal: Meal = Path(
        description="The meal in which the food item is located.",
        examples=["lunch"],
        title="Meal",
        alias="meal",
    ),
    food_id: str = Path(
        description="The ID of the food item to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food ID",
        alias="food_id",
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
) -> Literal[True]:
    result = await _inc_food(plan_id, meal, food_id, user_id, 1)

    if result.matched_count == 1:
        return True

    result = await plans_collection.update_one(
        _plan_filter(plan_id, user_id),
        {
            "$push": {
                meal: {
                    "food_id": food_id,
                    "count": 1,
                    "consumed_at_timestamp": None,
                }
            }
        },
    )

    if result.modified_count != 1:
        raise HTTPException(status_code=404, detail="Plan not found")

    return True


@router.post(
    "/myplan/{plan_id}/{meal}/remove/{food_id}",
    name="Remove Food Item from Meal",
    status_code=200,
    response_model=bool,
    response_description="Whether the food item was successfully removed from the meal.",
    summary="Remove a food item from a meal",
    description="Remove a specific food item from a meal in the user's meal plan. If the food item's count reaches 0, it will be removed from the meal.",
    responses={
        200: {"description": "Food item removed from meal successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "Plan not found."},
        422: {"description": "Validation error. Invalid plan ID, meal, or food ID."},
    },
)
async def remove_food_from_meal(
    plan_id: str = Path(
        description="The ID of the meal plan to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Plan ID",
        alias="plan_id",
    ),
    meal: Meal = Path(
        description="The meal in which the food item is located.",
        examples=["lunch"],
        title="Meal",
        alias="meal",
    ),
    food_id: str = Path(
        description="The ID of the food item to update.",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food ID",
        alias="food_id",
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
) -> Literal[True]:
    result = await _inc_food(plan_id, meal, food_id, user_id, -1)

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan = await plans_collection.find_one(_plan_filter(plan_id, user_id))

    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if any(f["food_id"] == food_id and f["count"] <= 0 for f in plan.get(meal, [])):
        await plans_collection.update_one(
            _plan_filter(plan_id, user_id),
            {"$pull": {meal: {"food_id": food_id}}},
        )

    return True
