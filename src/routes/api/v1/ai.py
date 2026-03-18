from __future__ import annotations

import uuid
from typing import TypedDict, cast

import arrow
from fastapi import APIRouter, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import ORJSONResponse as JSONResponse
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from starlette.status import (
    HTTP_200_OK,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_410_GONE,
    HTTP_423_LOCKED,
)

from src.app import app
from src.models import (
    AccountStatus,
    AuthenticationProvider,
    CredentialsDict,
    ExerciseDict,
    ExerciseModel,
    FoodItemDict,
    FoodReferenceModel,
    MyPlanDict,
    MyPlanModel,
    UserDict,
    UserExerciseDict,
    UserExerciseModel,
)
from src.routes.api.utils import get_user_id
from src.utils import S3, DailyInsightModel, GoogleAPIHandler

from .objects import ErrorResponseModel, TimestampRange

google_api_handler: GoogleAPIHandler = app.state.google_api_handler
database: Database = app.state.mongo_database
s3: S3 = app.state.s3

tips_collection: Collection["DailyInsightDict"] = database["tips"]
users_collection: Collection[UserDict] = database["users"]
credentials_collection: Collection[CredentialsDict] = database["credentials"]
exercises_collection: Collection[ExerciseDict] = database["exercises"]
foods_collection: Collection[FoodItemDict] = database["foods"]
plans_collection: Collection[MyPlanDict] = database["plans"]

user_exercises_collection: Collection[UserExerciseDict] = database["user_exercises"]

router = APIRouter(prefix="/ai", tags=["AI Content"])


class DailyInsightDict(TypedDict):
    _id: str
    user_id: str
    todays_focus: str
    daily_tip: str
    created_at_timestamp: float


def _today_window(tz: str = "Asia/Kolkata", /) -> tuple[float, float]:
    """Return start/end float timestamps for the current day in the given timezone."""
    now = arrow.now(tz)
    start_of_the_day = now.floor("day")
    end_of_the_day = now.ceil("day")
    return (
        start_of_the_day.float_timestamp,
        end_of_the_day.float_timestamp,
    )


async def _get_verified_user(user_id: str) -> UserDict:
    """Fetch user + credentials ensuring the account is active and email verified.

    Raises HTTPException with codes 404 (missing credentials), 410 (deleted),
    403 (locked or unverified), or 423 (user document missing).
    """
    cred = await credentials_collection.find_one({"_id": user_id})
    if not cred:
        raise HTTPException(HTTP_404_NOT_FOUND)

    if cred.get("account_status") == AccountStatus.DELETED:
        raise HTTPException(HTTP_410_GONE)

    if cred.get("account_status") == AccountStatus.LOCKED:
        raise HTTPException(HTTP_403_FORBIDDEN)

    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(
            HTTP_423_LOCKED,
        )

    if cred.get("verified_email", False):
        return user

    authentication_providers = cred.get("authentication_providers") or []
    if (
        AuthenticationProvider.APPLE.value in authentication_providers
        or AuthenticationProvider.GOOGLE.value in authentication_providers
    ):
        return user

    raise HTTPException(HTTP_403_FORBIDDEN)


@router.post(
    "/search/tips",
    response_class=JSONResponse,
    response_model=list[DailyInsightDict],
    response_description="A list of daily insights matching the search criteria.",
    summary="Search daily tips",
    description="Search for daily tips within a specified timestamp range.",
    responses={
        HTTP_403_FORBIDDEN: {
            "description": "User not verified or forbidden.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User credentials not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {"description": "Account deleted.", "model": ErrorResponseModel, "content": {"application/json": {}}},
        HTTP_423_LOCKED: {
            "description": "User account locked or profile missing.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def fetch_all_tips(
    timestamp_range: TimestampRange = Body(...),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    await _get_verified_user(user_id)

    cursor = tips_collection.find(
        {
            "user_id": user_id,
            "created_at_timestamp": {
                "$gte": timestamp_range.start_timestamp,
                "$lte": timestamp_range.end_timestamp,
            },
        }
    )

    tips = await cursor.to_list(length=None)
    return JSONResponse(
        [DailyInsightModel(todays_focus=tip["todays_focus"], daily_tip=tip["daily_tip"]).model_dump(by_alias=True) for tip in tips]
    )


@router.post(
    "/search/plan",
    response_class=JSONResponse,
    response_model=list[MyPlanModel],
    response_description="A list of meal plans matching the search criteria.",
    summary="Search meal plans",
    description="Search for meal plans within a specified timestamp range.",
    responses={
        HTTP_403_FORBIDDEN: {
            "description": "User not verified or forbidden.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User credentials not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {"description": "Account deleted.", "model": ErrorResponseModel, "content": {"application/json": {}}},
        HTTP_423_LOCKED: {
            "description": "User account locked or profile missing.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def fetch_all_plans(
    timestamp_range: TimestampRange = Body(...),
    user_id: str = Depends(get_user_id, use_cache=False),
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

    plans = await cursor.to_list(length=None)
    return JSONResponse(
        [
            MyPlanModel(
                _id=plan.get("_id"),  # type: ignore
                user_id=plan.get("user_id"),
                breakfast=[FoodReferenceModel(**item) for item in plan.get("breakfast", [])],
                lunch=[FoodReferenceModel(**item) for item in plan.get("lunch", [])],
                dinner=[FoodReferenceModel(**item) for item in plan.get("dinner", [])],
                snacks=[FoodReferenceModel(**item) for item in plan.get("snacks", [])],
                created_at_timestamp=plan.get("created_at_timestamp"),
            ).model_dump(by_alias=True)
            for plan in plans
        ]
    )


@router.post(
    "/search/exercises",
    response_class=JSONResponse,
    response_model=list[UserExerciseModel],
    response_description="A list of exercises matching the search criteria.",
    summary="Search exercises",
    description="Search for exercises within a specified timestamp range.",
    responses={
        HTTP_403_FORBIDDEN: {
            "description": "User not verified or forbidden.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User credentials not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {
            "description": "Account deleted.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_423_LOCKED: {
            "description": "User account locked or profile missing.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def fetch_all_exercises(
    timestamp_range: TimestampRange = Body(...),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    await _get_verified_user(user_id)

    start_ts = timestamp_range.start_timestamp
    end_ts = timestamp_range.end_timestamp

    cursor = user_exercises_collection.find(
        {
            "user_id": user_id,
            "added_at_timestamp": {
                "$gte": start_ts,
                "$lte": end_ts,
            },
        }
    )

    exercises = await cursor.to_list(length=None)
    return JSONResponse([UserExerciseModel(**exercise).model_dump(by_alias=True) for exercise in exercises])


@router.get(
    "/generate/plan",
    response_model=MyPlanModel,
    status_code=HTTP_200_OK,
    response_description="The generated meal plan for the user.",
    summary="Generate meal plan",
    description="Generate a meal plan for the user based on their dietary preferences and food intolerances.",
    responses={
        HTTP_403_FORBIDDEN: {
            "description": "User not verified or forbidden.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User credentials not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {"description": "Account deleted.", "model": ErrorResponseModel, "content": {"application/json": {}}},
        HTTP_423_LOCKED: {
            "description": "User account locked or profile missing.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def get_meal_plan(user_id: str = Depends(get_user_id, use_cache=False)):
    """Return today's meal plan if it exists; otherwise generate, persist, and return one."""
    user: UserDict = await _get_verified_user(user_id)
    timezone = user.get("timezone") or "Asia/Kolkata"
    start, end = _today_window(timezone)
    existing_plan = await plans_collection.find_one(
        {
            "user_id": user_id,
            "created_at_timestamp": {
                "$gte": start,
                "$lte": end,
            },
        }
    )
    if existing_plan:
        model = MyPlanModel(
            _id=existing_plan.get("_id"),  # type: ignore
            user_id=existing_plan.get("user_id"),
            breakfast=[FoodReferenceModel(**item) for item in existing_plan.get("breakfast", [])],
            lunch=[FoodReferenceModel(**item) for item in existing_plan.get("lunch", [])],
            dinner=[FoodReferenceModel(**item) for item in existing_plan.get("dinner", [])],
            snacks=[FoodReferenceModel(**item) for item in existing_plan.get("snacks", [])],
            created_at_timestamp=existing_plan.get("created_at_timestamp"),
        )
        return JSONResponse(model.model_dump(by_alias=True))

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

    return JSONResponse(plan.model_dump(by_alias=True))


@router.get(
    "/generate/exercises",
    response_model=list[UserExerciseModel],
    response_description="A list of exercises generated for the user.",
    summary="Generate exercises",
    description="Generate a list of exercises for the user based on their profile and past exercise history.",
    responses={
        HTTP_403_FORBIDDEN: {
            "description": "User not verified or forbidden.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User credentials not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {"description": "Account deleted.", "model": ErrorResponseModel, "content": {"application/json": {}}},
        HTTP_423_LOCKED: {
            "description": "User account locked or profile missing.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def get_exercises(user_id: str = Depends(get_user_id, use_cache=False)):
    """Return today's exercises if present; otherwise generate, store, and return new ones."""
    user = await _get_verified_user(user_id)
    timezone = user.get("timezone") or "Asia/Kolkata"
    window_start_ts, window_end_ts = _today_window(timezone)

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
        ExerciseModel(**exercise).model_dump(by_alias=True, mode="json") async for exercise in exercises_collection.find({})
    ]

    ai_response = await google_api_handler.generate_exercises(
        user=user,
        exercise_sets=exercise_catalog_payload,
    )

    now_ts = arrow.now().float_timestamp
    created_user_exercises: list[UserExerciseDict] = []

    for exercise in ai_response.exercises:
        name = exercise.name.lower().strip().replace(" ", "_").replace("'", "")
        exercise.image_name_uri = await s3.get_presigned_url(f"ExerciseImages/{name}.png")

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
    "/generate/tips",
    response_model=DailyInsightModel,
    status_code=HTTP_200_OK,
    response_description="The generated daily insight containing today's focus and a helpful tip.",
    summary="Generate daily tips",
    description="Generate daily tips including today's focus and a helpful tip for the user.",
    responses={
        HTTP_403_FORBIDDEN: {
            "description": "User not verified or forbidden.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User credentials not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {"description": "Account deleted.", "model": ErrorResponseModel, "content": {"application/json": {}}},
        HTTP_423_LOCKED: {
            "description": "User account locked or profile missing.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def get_tips(user_id: str = Depends(get_user_id, use_cache=False)):
    """Return today's tip for the verified user, generating and persisting it if absent."""
    user = await _get_verified_user(user_id)
    timezone = user.get("timezone") or "Asia/Kolkata"
    start, end = _today_window(timezone)

    tip = await tips_collection.find_one(
        {
            "user_id": user_id,
            "created_at_timestamp": {"$gte": start, "$lt": end},
        }
    )
    if tip:
        return JSONResponse(DailyInsightModel(daily_tip=tip["daily_tip"], todays_focus=tip["todays_focus"]).model_dump(by_alias=True))

    generated = await google_api_handler.generate_tips(user=user)
    await tips_collection.insert_one(
        {
            "_id": str(uuid.uuid4()),
            "user_id": user_id,
            "todays_focus": generated.todays_focus,
            "daily_tip": generated.daily_tip,
            "created_at_timestamp": arrow.now().float_timestamp,
        }
    )
    return JSONResponse(generated.model_dump(by_alias=True))
