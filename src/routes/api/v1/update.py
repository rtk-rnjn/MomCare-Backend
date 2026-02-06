from __future__ import annotations

from typing import Literal

import arrow
from fastapi import APIRouter, Body, Depends, HTTPException
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


@router.post("/exercise/{_id}")
async def update_exercise(
    _id: str, duration: float = Body(...), user_id: str = Depends(get_user_id)
):
    update_result = await exercises_collection.update_one(
        {"_id": _id, "user_id": user_id},
        {"$set": {"video_duration_completed_seconds": duration}},
    )
    return update_result.modified_count == 1


@router.post("/myplan/{plan_id}/{meal}/{food_id}/consume")
async def consume_food(
    plan_id: str,
    meal: Meal,
    food_id: str,
    user_id: str = Depends(get_user_id),
):
    return _update_consumed(plan_id, meal, food_id, user_id, arrow.now().timestamp())


@router.post("/myplan/{plan_id}/{meal}/{food_id}/unconsume")
async def unconsume_food(
    plan_id: str,
    meal: Meal,
    food_id: str,
    user_id: str = Depends(get_user_id),
):
    return _update_consumed(plan_id, meal, food_id, user_id, None)


@router.post("/myplan/{plan_id}/{meal}/add/{food_id}")
async def add_food_to_meal(
    plan_id: str,
    meal: Meal,
    food_id: str,
    user_id: str = Depends(get_user_id),
):
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


@router.post("/myplan/{plan_id}/{meal}/remove/{food_id}")
async def remove_food_from_meal(
    plan_id: str,
    meal: Meal,
    food_id: str,
    user_id: str = Depends(get_user_id),
):
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
