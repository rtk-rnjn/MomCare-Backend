from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.app import genai_handler, s3_client
from src.models import Exercise, MyPlan
from src.utils import Token
from src.utils.google_api_handler import YOGA_SETS, DailyInsight

from ..utils import data_handler, get_user_token

router = APIRouter(prefix="/ai", tags=["AI Content"])


@router.get("/plan", response_model=MyPlan)
async def get_plan(request: Request, token: Token = Depends(get_user_token)) -> MyPlan | None:
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

    return await genai_handler.generate_plan(user, foods_collection=data_handler.database_handler.foods_collection)


@router.get("/exercises", response_model=list[Exercise])
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

    data = await genai_handler.get_exercises(user)
    yoga_sets = data.yoga_sets if data else []
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
            name=yoga_set.name,
            image_uri=image_uri,
            description=yoga_set.description,
            duration=None,
            level=yoga_set.level,
            targeted_body_parts=yoga_set.targeted_body_parts,
            week=yoga_set.week,
            tags=yoga_set.tags,
        )
        sendable.append(exercise)

    return sendable


@router.get("/tips", response_model=DailyInsight | None)
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
