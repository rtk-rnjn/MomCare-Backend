from __future__ import annotations

import uuid
from typing import AsyncGenerator, TypedDict, cast

import arrow
from fastapi import APIRouter, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.cursor import AsyncCursor
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import (
    ExerciseDict,
    ExerciseModel,
    FoodItemDict,
    MyPlanDict,
    MyPlanModel,
    UserDict,
    UserExerciseDict,
    UserExerciseModel,
)
from src.routes.api.utils import get_user_id
from src.utils import S3, DailyInsight, GoogleAPIHandler

from .objects import TimestampRange

google_api_handler: GoogleAPIHandler = app.state.google_api_handler
database: Database = app.state.mongo_database
s3: S3 = app.state.s3

tips_collection: Collection = database["tips"]
users_collection: Collection[UserDict] = database["users"]
exercises_collection: Collection[ExerciseDict] = database["exercises"]
foods_collection: Collection[FoodItemDict] = database["foods"]
plans_collection: Collection[MyPlanDict] = database["plans"]

user_exercises_collection: Collection[UserExerciseDict] = database["user_exercises"]

router = APIRouter(prefix="/ai", tags=["AI Content"])


DailyInsightDict = TypedDict(
    "DailyInsightDict",
    {
        "_id": str,
        "todays_focus": str,
        "daily_tip": str,
        "created_at_timestamp": float,
    },
)


def _today_window() -> tuple[float, float]:
    now = arrow.now()
    return (
        now.shift(days=-1).float_timestamp,
        now.shift(days=1).float_timestamp,
    )


async def _get_verified_user(user_id: str) -> UserDict:
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(404, "User not found.")
    if not user.get("verified_email", False):
        raise HTTPException(403, "Email not verified.")
    return user


def _exercise_pipeline(user_id: str, start: float, end: float) -> list[dict]:
    return [
        {
            "$match": {
                "user_id": user_id,
                "added_at_timestamp": {"$gte": start, "$lte": end},
            }
        },
        {
            "$lookup": {
                "from": "exercises",
                "let": {"exerciseId": "$exercise_id"},
                "pipeline": [{"$match": {"$expr": {"$eq": ["$_id", "$$exerciseId"]}}}],
                "as": "exercise",
            }
        },
        {"$unwind": "$exercise"},
    ]


async def _hydrate_exercise(exercise: ExerciseDict) -> ExerciseModel:
    model = ExerciseModel(**exercise)
    model.image_name_uri = await s3.get_presigned_url(f"ExerciseImages/{model.image_name}")
    return model


async def _stream_json(*, cursor: AsyncGenerator | AsyncCursor, model_factory: type[BaseModel]):
    async for m in cursor:
        yield model_factory(**m).model_dump_json(by_alias=True) + "\n"


@router.get(
    "/generate/tips",
    response_model=DailyInsight,
    response_description="The generated daily insight containing today's focus and a helpful tip.",
    summary="Generate daily tips",
    description="Generate daily tips including today's focus and a helpful tip for the user.",
    responses={
        200: {"description": "Daily tips generated successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        403: {"description": "Forbidden. User email not verified."},
        404: {"description": "User not found."},
    },
)
async def get_tips(user_id: str = Depends(get_user_id)):
    user = await _get_verified_user(user_id)
    start, end = _today_window()

    tip = await tips_collection.find_one(
        {
            "_id": user_id,
            "created_at_timestamp": {"$gte": start, "$lt": end},
        }
    )
    if tip:
        return DailyInsight(**tip)

    generated = await google_api_handler.generate_tips(user=user)
    await tips_collection.insert_one(
        {
            "_id": user_id,
            **generated.model_dump(),
            "created_at_timestamp": arrow.now().float_timestamp,
        }
    )
    return generated


@router.get(
    "/search/tips",
    response_class=StreamingResponse,
    response_model=list[DailyInsight],
    response_description="A list of daily insights matching the search criteria.",
    summary="Search daily tips",
    description="Search for daily tips within a specified timestamp range.",
    responses={
        200: {"description": "Daily tips retrieved successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
        403: {"description": "Forbidden. User email not verified."},
    },
)
async def fetch_all_tips(
    timestamp_range: TimestampRange = Body(...),
    user_id: str = Depends(get_user_id),
):
    await _get_verified_user(user_id)

    cursor = tips_collection.find(
        {
            "_id": user_id,
            "created_at_timestamp": {
                "$gte": timestamp_range.start_timestamp,
                "$lte": timestamp_range.end_timestamp,
            },
        }
    )

    return StreamingResponse(
        _stream_json(cursor=cursor, model_factory=DailyInsight),
        media_type="application/json",
    )


@router.get(
    "/search/plan",
    response_class=StreamingResponse,
    response_model=list[MyPlanModel],
    response_description="A list of meal plans matching the search criteria.",
    summary="Search meal plans",
    description="Search for meal plans within a specified timestamp range.",
    responses={
        200: {"description": "Meal plans retrieved successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
        403: {"description": "Forbidden. User email not verified."},
    },
)
async def fetch_all_plans(
    timestamp_range: TimestampRange = Body(...),
    user_id: str = Depends(get_user_id),
):
    await _get_verified_user(user_id)

    cursor = plans_collection.find(
        {
            "user_id": user_id,
            "created_at_timestamp": {
                "$gte": timestamp_range.start_timestamp,
                "$lte": timestamp_range.end_timestamp,
            },
        }
    )

    return StreamingResponse(
        _stream_json(cursor=cursor, model_factory=MyPlanModel),
        media_type="application/json",
    )


@router.get(
    "/generate/plan",
    response_class=StreamingResponse,
    response_model=MyPlanModel,
    response_description="The generated meal plan for the user.",
    summary="Generate meal plan",
    description="Generate a meal plan for the user based on their dietary preferences and food intolerances.",
    responses={
        200: {"description": "Meal plan generated successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
        403: {"description": "Forbidden. User email not verified."},
    },
)
async def get_meal_plan(user_id: str = Depends(get_user_id)):
    user: UserDict = await _get_verified_user(user_id)

    now = arrow.now()
    existing_plan = await plans_collection.find_one(
        {
            "user_id": user_id,
            "created_at_timestamp": {
                "$gte": now.shift(days=-1).float_timestamp,
                "$lte": now.shift(days=1).float_timestamp,
            },
        }
    )
    if existing_plan:
        return MyPlanModel(**existing_plan)  # type: ignore

    food_intolerances = user.get("food_intolerances", [])
    dietary_preferences = user.get("dietary_preferences", [])

    pipeline: list[dict] = []

    if food_intolerances:
        pipeline.append({"$match": {"allergic_ingredients": {"$not": {"$elemMatch": {"$in": food_intolerances}}}}})

    if dietary_preferences:
        pipeline.append({"$match": {"type": {"$in": dietary_preferences}}})

    foods_cursor = await foods_collection.aggregate(pipeline)
    foods = [{"_id": food.get("_id"), "name": food.get("name")} async for food in foods_cursor]

    plan = await google_api_handler.generate_plan(user=user, available_foods=foods)

    plan.created_at_timestamp = arrow.now().float_timestamp
    plan.user_id = user_id
    plan.id = str(uuid.uuid4())

    plan_dict = cast(MyPlanDict, plan.model_dump(by_alias=True, mode="json"))
    await plans_collection.insert_one(plan_dict)

    return plan


@router.get(
    "/generate/exercises",
    response_class=StreamingResponse,
    response_model=list[UserExerciseModel],
    response_description="A list of exercises generated for the user.",
    summary="Generate exercises",
    description="Generate a list of exercises for the user based on their profile and past exercise history.",
    responses={
        200: {"description": "Exercises generated successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
        403: {"description": "Forbidden. User email not verified."},
    },
)
async def get_exercises(user_id: str = Depends(get_user_id)):
    user = await _get_verified_user(user_id)
    window_start_ts, window_end_ts = _today_window()

    existing_user_exercises = await user_exercises_collection.find(
        {
            "user_id": user_id,
            "added_at_timestamp": {
                "$gte": window_start_ts,
                "$lte": window_end_ts,
            },
        }
    ).to_list(length=None)

    if existing_user_exercises:
        return JSONResponse(existing_user_exercises)

    exercise_catalog_payload = [
        ExerciseModel(**exercise).model_dump(by_alias=True, mode="json") for exercise in exercises_collection.find({})
    ]

    ai_response = await google_api_handler.generate_exercises(
        user=user,
        exercise_sets=exercise_catalog_payload,
    )

    now_ts = arrow.now().float_timestamp
    created_user_exercises: list[UserExerciseDict] = []

    for exercise in ai_response.exercises:
        exercise.image_name_uri = await s3.get_presigned_url(f"ExerciseImages/{exercise.image_name}")

        user_exercise_record = UserExerciseDict(
            _id=str(uuid.uuid4()),
            user_id=user_id,
            exercise_id=exercise.id,
            added_at_timestamp=now_ts,
            video_duration_completed_seconds=0.0,
        )

        await user_exercises_collection.insert_one(user_exercise_record)
        created_user_exercises.append(user_exercise_record)

    return JSONResponse(created_user_exercises)


@router.get(
    "/search/exercises",
    response_class=StreamingResponse,
    response_model=list[ExerciseModel],
    response_description="A list of exercises matching the search criteria.",
    summary="Search exercises",
    description="Search for exercises within a specified timestamp range.",
    responses={
        200: {"description": "Exercises retrieved successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
        403: {"description": "Forbidden. User email not verified."},
    },
)
async def fetch_all_exercises(
    timestamp_range: TimestampRange = Body(...),
    user_id: str = Depends(get_user_id),
):
    await _get_verified_user(user_id)

    pipeline = _exercise_pipeline(
        user_id,
        timestamp_range.start_timestamp,
        timestamp_range.end_timestamp,
    )

    cursor = await user_exercises_collection.aggregate(pipeline)
    models = (await _hydrate_exercise(doc["exercise"]) async for doc in cursor if "exercise" in doc)

    return StreamingResponse(
        _stream_json(cursor=models, model_factory=ExerciseModel),
        media_type="application/json",
    )
