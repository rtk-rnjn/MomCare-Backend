from __future__ import annotations

from typing import ParamSpec, TypedDict, TypeVar

import arrow
from fastapi import APIRouter, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import ORJSONResponse as JSONResponse
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis
from starlette.status import (
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

from ..objects import ErrorResponseModel, TimestampRange

google_api_handler: GoogleAPIHandler = app.state.google_api_handler
database: Database = app.state.mongo_database
s3: S3 = app.state.s3
redis_client: Redis = app.state.redis_client

tips_collection: Collection["DailyInsightDict"] = database["tips"]
users_collection: Collection[UserDict] = database["users"]
credentials_collection: Collection[CredentialsDict] = database["credentials"]
exercises_collection: Collection[ExerciseDict] = database["exercises"]
foods_collection: Collection[FoodItemDict] = database["foods"]
plans_collection: Collection[MyPlanDict] = database["plans"]

user_exercises_collection: Collection[UserExerciseDict] = database["user_exercises"]

router = APIRouter(prefix="/search", tags=["AI Content"])

P = ParamSpec("P")
T = TypeVar("T")


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
    user = await users_collection.find_one({"_id": user_id})

    if not cred:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="User credentials not found.")

    authentication_providers = cred.get("authentication_providers") or []
    if AuthenticationProvider.APPLE.value in authentication_providers and user is not None:
        return user

    if cred.get("account_status") == AccountStatus.DELETED:
        raise HTTPException(HTTP_410_GONE, detail="This account has been deleted.")

    if cred.get("account_status") == AccountStatus.LOCKED:
        raise HTTPException(HTTP_423_LOCKED, detail="Your account is locked. Please contact support.")

    if not user:
        raise HTTPException(HTTP_404_NOT_FOUND, detail="User profile is missing or unavailable.")

    if cred.get("verified_email", False):
        return user

    raise HTTPException(HTTP_403_FORBIDDEN, detail="Your email address has not been verified. Please verify your email to continue.")


@router.post(
    "/tips",
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
    "/plan",
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
                original_breakfast=[FoodReferenceModel(**item) for item in plan.get("original_breakfast", [])],
                original_lunch=[FoodReferenceModel(**item) for item in plan.get("original_lunch", [])],
                original_dinner=[FoodReferenceModel(**item) for item in plan.get("original_dinner", [])],
                original_snacks=[FoodReferenceModel(**item) for item in plan.get("original_snacks", [])],
                created_at_timestamp=plan.get("created_at_timestamp"),
            ).model_dump(by_alias=True)
            for plan in plans
        ]
    )


@router.post(
    "/exercises",
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
