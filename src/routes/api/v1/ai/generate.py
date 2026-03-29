from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, ParamSpec, TypedDict, TypeVar, cast

import arrow
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import ORJSONResponse as JSONResponse
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis
from starlette.status import (
    HTTP_200_OK,
    HTTP_202_ACCEPTED,
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

from ..objects import ErrorResponseModel

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

router = APIRouter(prefix="/generate", tags=["AI Content"])

logger = logging.getLogger(__name__)

DEFAULT_LONG_POLL_SECONDS = 25.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_LOCK_TTL_SECONDS = 300

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


def _timezone_for_user(user: UserDict) -> str:
    return user.get("timezone") or "Asia/Kolkata"


def _daily_lock_key(kind: str, user: UserDict) -> str:
    day_key = arrow.now(_timezone_for_user(user)).format("YYYY-MM-DD")
    return f"locks:{kind}:{user.get('_id')}:{day_key}"


async def _acquire_task_lock(lock_key: str, ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS) -> bool:
    return bool(await redis_client.set(lock_key, "1", ex=ttl_seconds, nx=True))


async def _long_poll(fetch_existing: Callable[[], Awaitable[Any]], *, timeout_seconds: float, interval_seconds: float):
    if timeout_seconds <= 0:
        return None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        existing = await fetch_existing()
        if existing:
            return existing

        if loop.time() >= deadline:
            return None

        await asyncio.sleep(interval_seconds)


async def _get_verified_user(user_id: str) -> UserDict:
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


async def _find_plan_for_today(user: UserDict):
    start, end = _today_window(_timezone_for_user(user))
    return await plans_collection.find_one(
        {
            "user_id": user.get("_id"),
            "created_at_timestamp": {
                "$gte": start,
                "$lte": end,
            },
        }
    )


async def _has_existing_plan_for_today(user: UserDict):
    existing_plan = await _find_plan_for_today(user)
    if existing_plan:
        model = MyPlanModel(
            _id=existing_plan.get("_id"),  # type: ignore
            user_id=existing_plan.get("user_id"),
            breakfast=[FoodReferenceModel(**item) for item in existing_plan.get("breakfast", [])],
            lunch=[FoodReferenceModel(**item) for item in existing_plan.get("lunch", [])],
            dinner=[FoodReferenceModel(**item) for item in existing_plan.get("dinner", [])],
            snacks=[FoodReferenceModel(**item) for item in existing_plan.get("snacks", [])],
            original_breakfast=[FoodReferenceModel(**item) for item in existing_plan.get("original_breakfast", [])],
            original_lunch=[FoodReferenceModel(**item) for item in existing_plan.get("original_lunch", [])],
            original_dinner=[FoodReferenceModel(**item) for item in existing_plan.get("original_dinner", [])],
            original_snacks=[FoodReferenceModel(**item) for item in existing_plan.get("original_snacks", [])],
            created_at_timestamp=existing_plan.get("created_at_timestamp"),
        )
        return JSONResponse(model.model_dump(by_alias=True))


async def _load_available_foods(user: UserDict) -> list[dict[str, Any]]:
    food_intolerances = user.get("food_intolerances", [])
    dietary_preferences = user.get("dietary_preferences", [])

    pipeline: list[dict[str, Any]] = []

    if food_intolerances:
        pipeline.append({"$match": {"allergic_ingredients": {"$not": {"$elemMatch": {"$in": food_intolerances}}}}})

    if dietary_preferences:
        pipeline.append({"$match": {"type": {"$in": dietary_preferences}}})

    foods_cursor = await foods_collection.aggregate(pipeline)
    return [{"_id": food.get("_id"), "name": food.get("name")} async for food in foods_cursor]


async def _generate_and_store_plan(user: UserDict, user_id: str, available_foods: list[dict[str, Any]], lock_key: str):
    try:
        if await _find_plan_for_today(user):
            return

        partial_plan = await google_api_handler.generate_plan(user=user, available_foods=available_foods)

        plan = MyPlanModel(
            _id="",
            user_id=user_id,
            breakfast=partial_plan.breakfast,
            lunch=partial_plan.lunch,
            dinner=partial_plan.dinner,
            snacks=partial_plan.snacks,
            original_breakfast=partial_plan.breakfast,
            original_lunch=partial_plan.lunch,
            original_dinner=partial_plan.dinner,
            original_snacks=partial_plan.snacks,
            created_at_timestamp=0.0,
        )

        plan.created_at_timestamp = arrow.now(_timezone_for_user(user)).float_timestamp
        plan.id = str(uuid.uuid4())

        plan_dict = cast(MyPlanDict, plan.model_dump(by_alias=True, mode="json"))

        if await _find_plan_for_today(user):
            return

        await plans_collection.insert_one(plan_dict)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to generate plan for user %s", user_id, exc_info=exc)
    finally:
        await redis_client.delete(lock_key)


@router.get(
    "/plan",
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
        HTTP_202_ACCEPTED: {"description": "Generation in progress.", "content": {"application/json": {}}},
    },
)
async def get_meal_plan(_background_tasks: BackgroundTasks, user_id: str = Depends(get_user_id, use_cache=False)):
    """Return today's meal plan if it exists; otherwise enqueue generation and long-poll for the result."""
    wait_seconds = DEFAULT_LONG_POLL_SECONDS
    poll_interval_seconds = DEFAULT_POLL_INTERVAL_SECONDS

    user: UserDict = await _get_verified_user(user_id)
    existing_plan = await _has_existing_plan_for_today(user)
    if existing_plan:
        return existing_plan

    available_foods = await _load_available_foods(user)

    lock_key = _daily_lock_key("plan", user)
    if await _acquire_task_lock(lock_key):
        asyncio.create_task(_generate_and_store_plan(user, user_id, available_foods, lock_key))

    polled_plan = await _long_poll(
        lambda: _has_existing_plan_for_today(user),
        timeout_seconds=wait_seconds,
        interval_seconds=poll_interval_seconds,
    )
    if polled_plan:
        return polled_plan

    return JSONResponse(
        {
            "status": "processing",
            "task_id": lock_key,
            "detail": "Meal plan generation is in progress. Retry shortly.",
            "retry_after_seconds": poll_interval_seconds,
        },
        status_code=HTTP_202_ACCEPTED,
    )


async def _find_exercises_for_today(user: UserDict):
    start, end = _today_window(_timezone_for_user(user))
    return await user_exercises_collection.find(
        {
            "user_id": user.get("_id"),
            "added_at_timestamp": {
                "$gte": start,
                "$lte": end,
            },
        }
    ).to_list(length=None)


async def _has_existing_exercises_for_today(user: UserDict):
    existing_exercises = await _find_exercises_for_today(user)
    if existing_exercises:
        return JSONResponse([UserExerciseModel(**exercise).model_dump(by_alias=True) for exercise in existing_exercises])


async def _fetch_exercise_catalog_payload():
    return [ExerciseModel(**exercise).model_dump(by_alias=True, mode="json") async for exercise in exercises_collection.find({})]


async def _generate_and_store_exercises(user: UserDict, user_id: str, lock_key: str):
    try:
        if await _find_exercises_for_today(user):
            return

        exercise_catalog_payload = await _fetch_exercise_catalog_payload()

        ai_response = await google_api_handler.generate_exercises(
            user=user,
            exercise_sets=exercise_catalog_payload,
        )

        now_ts = arrow.now(_timezone_for_user(user)).float_timestamp
        if await _find_exercises_for_today(user):
            return

        payload = []

        for exercise in ai_response.exercises:
            name = exercise.name.lower().strip().replace(" ", "_").replace("'", "")
            exercise.image_name_uri = await s3.get_presigned_url(f"ExerciseImages/{name}.png")

            payload.append(
                UserExerciseDict(
                    _id=str(uuid.uuid4()),
                    user_id=user_id,
                    exercise_id=exercise.id,
                    added_at_timestamp=now_ts,
                    video_duration_completed_seconds=0.0,
                )
            )

        await user_exercises_collection.insert_many(payload)

    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to generate exercises for user %s", user_id, exc_info=exc)
    finally:
        await redis_client.delete(lock_key)


async def _find_tip_for_today(user: UserDict):
    start, end = _today_window(_timezone_for_user(user))
    return await tips_collection.find_one(
        {
            "user_id": user.get("_id"),
            "created_at_timestamp": {"$gte": start, "$lt": end},
        }
    )


async def _generate_and_store_tip(user: UserDict, user_id: str, lock_key: str):
    try:
        if await _find_tip_for_today(user):
            return

        generated = await google_api_handler.generate_tips(user=user)

        if await _find_tip_for_today(user):
            return

        await tips_collection.insert_one(
            {
                "_id": str(uuid.uuid4()),
                "user_id": user_id,
                "todays_focus": generated.todays_focus,
                "daily_tip": generated.daily_tip,
                "created_at_timestamp": arrow.now(_timezone_for_user(user)).float_timestamp,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Failed to generate tips for user %s", user_id, exc_info=exc)
    finally:
        await redis_client.delete(lock_key)


@router.get(
    "/exercises",
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
        HTTP_202_ACCEPTED: {"description": "Generation in progress.", "content": {"application/json": {}}},
    },
)
async def get_exercises(user_id: str = Depends(get_user_id, use_cache=False)):
    """Return today's exercises if present; otherwise enqueue generation and long-poll for the result."""
    wait_seconds = DEFAULT_LONG_POLL_SECONDS
    poll_interval_seconds = DEFAULT_POLL_INTERVAL_SECONDS

    user = await _get_verified_user(user_id)
    existing_exercises = await _has_existing_exercises_for_today(user)
    if existing_exercises:
        return existing_exercises

    lock_key = _daily_lock_key("exercises", user)
    if await _acquire_task_lock(lock_key):
        asyncio.create_task(_generate_and_store_exercises(user, user_id, lock_key))

    polled_exercises = await _long_poll(
        lambda: _has_existing_exercises_for_today(user),
        timeout_seconds=wait_seconds,
        interval_seconds=poll_interval_seconds,
    )
    if polled_exercises:
        return polled_exercises

    return JSONResponse(
        {
            "status": "processing",
            "task_id": lock_key,
            "detail": "Exercise generation is in progress. Retry shortly.",
            "retry_after_seconds": poll_interval_seconds,
        },
        status_code=HTTP_202_ACCEPTED,
    )


@router.get(
    "/tips",
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
        HTTP_202_ACCEPTED: {"description": "Generation in progress.", "content": {"application/json": {}}},
    },
)
async def get_tips(user_id: str = Depends(get_user_id, use_cache=False)):
    """Return today's tip for the verified user, generating and persisting it if absent."""
    wait_seconds = DEFAULT_LONG_POLL_SECONDS
    poll_interval_seconds = DEFAULT_POLL_INTERVAL_SECONDS

    user = await _get_verified_user(user_id)

    tip = await _find_tip_for_today(user)
    if tip:
        return JSONResponse(DailyInsightModel(daily_tip=tip["daily_tip"], todays_focus=tip["todays_focus"]).model_dump(by_alias=True))

    lock_key = _daily_lock_key("tips", user)
    if await _acquire_task_lock(lock_key):
        asyncio.create_task(_generate_and_store_tip(user, user_id, lock_key))

    polled_tip = await _long_poll(
        lambda: _find_tip_for_today(user),
        timeout_seconds=wait_seconds,
        interval_seconds=poll_interval_seconds,
    )

    if polled_tip:
        return JSONResponse(
            DailyInsightModel(daily_tip=polled_tip["daily_tip"], todays_focus=polled_tip["todays_focus"]).model_dump(by_alias=True)
        )

    return JSONResponse(
        {
            "status": "processing",
            "task_id": lock_key,
            "detail": "Daily tip generation is in progress. Retry shortly.",
            "retry_after_seconds": poll_interval_seconds,
        },
        status_code=HTTP_202_ACCEPTED,
    )
