from __future__ import annotations

import json
import time
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse as _JSONResponse

from src.app import genai_handler, s3_client
from src.models.exercise import ExerciseDict as Exercise
from src.models.myplan import MyPlanDict
from src.utils import Token
from src.utils.google_api_handler import YOGA_SETS, YogaSet

from ..utils import data_handler, get_user_token

router = APIRouter(prefix="/ai", tags=["AI Content"])

encoder_map = {
    ObjectId: str,
}


class AnyEncoder(json.JSONEncoder):
    def default(self, o):
        if type(o) in encoder_map:
            return encoder_map[type(o)](o)
        return super().default(o)


class JSONResponse(_JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
            cls=AnyEncoder,
        ).encode("utf-8")


@router.get("/plan")
async def get_plan(request: Request, token: Token = Depends(get_user_token)):
    """
    Generate AI-powered personalized nutrition plan for the user.

    Creates a comprehensive meal plan based on the user's medical data, dietary preferences,
    pregnancy stage, and nutritional requirements. Uses AI to recommend appropriate foods
    for maternal wellness.
    """
    user_id = token.sub

    user = await data_handler.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today_plan = await data_handler.get_todays_plan(user_id)
    if today_plan:
        return JSONResponse(content=today_plan)

    try:
        myplan = await genai_handler.generate_plan(user, foods_collection=data_handler.foods_collection)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    plan = MyPlanDict(
        _id=ObjectId(),
        user_id=user_id,
        breakfast=myplan.get("breakfast", []),
        lunch=myplan.get("lunch", []),
        snacks=myplan.get("snacks", []),
        dinner=myplan.get("dinner", []),
        created_at_timestamp=time.time(),
    )

    await data_handler.save_myplan(plan)

    return JSONResponse(content=plan)


@router.get("/exercises")
async def get_exercises(token: Token = Depends(get_user_token)):
    """
    Get personalized exercise recommendations for maternal fitness.

    Provides exercise routines tailored to the user's pregnancy stage, fitness level,
    and health conditions. Includes safe prenatal and postpartum exercises.
    """
    user_id = token.sub

    user = await data_handler.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    today_exercises = await data_handler.get_todays_exercises(user_id)
    if today_exercises:
        return JSONResponse(content=today_exercises)

    data = await genai_handler.get_exercises(user)
    yoga_sets: list[YogaSet] = data.yoga_sets if data else []
    if not yoga_sets:
        return []

    sendable = []
    for yoga_set in yoga_sets:
        yoga = list(filter(lambda x: x["name"] == yoga_set.name, YOGA_SETS))
        if yoga:
            image_uri = await s3_client.get_presigned_url(f"ExerciseImages/{yoga[0]['image_uri']}")
        else:
            image_uri = None

        exercise = Exercise(
            user_id=user_id,
            name=yoga_set.name,
            image_uri=image_uri,
            exercise_type="Yoga",
            description=yoga_set.description,
            duration=None,
            level=yoga_set.level,
            targeted_body_parts=yoga_set.targeted_body_parts,
            week=yoga_set.week,
            tags=yoga_set.tags,
            assigned_at_timestamp=time.time(),
        )
        sendable.append(exercise)

    await data_handler.save_exercises(sendable)

    return JSONResponse(content=sendable)


@router.get("/tips")
async def get_tips(token: Token = Depends(get_user_token)):
    """
    Get personalized wellness tips and recommendations.

    AI-generated tips based on user's current pregnancy stage, health data,
    and preferences. Includes nutrition advice, exercise suggestions, and wellness guidance.
    """
    user_id = token.sub

    user = await data_handler.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_tips(user)
