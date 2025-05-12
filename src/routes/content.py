from __future__ import annotations

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.app import app, cache_handler, genai_handler
from src.models.food_item import FoodItem
from src.models.myplan import MyPlan
from src.utils import Token, TokenHandler

token_handler = TokenHandler(os.environ["JWT_SECRET"])
security = HTTPBearer()


def get_user_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return token_handler.decode_token(credentials.credentials)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


router = APIRouter(prefix="/plan", tags=["Plan"])


@router.get("/")
async def get_plan(request: Request) -> Optional[MyPlan]:
    user_id = "7CD207A2-754F-41BB-8EBC-23799FC410B1"

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_plan(user)


@router.get("/search")
async def search_food(request: Request, food_name: str, limit: int = 10) -> List[FoodItem]:
    foods: List[FoodItem] = []
    async for food in cache_handler.get_foods(food_name=food_name, limit=limit):
        foods.append(food)

    return foods


@router.get("/tips")
async def get_tips(token: Token = Depends(get_user_token)):
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_tips(user)


app.include_router(router)
