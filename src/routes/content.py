from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.app import app, cache_handler, genai_handler
from src.models.food_item import FoodItem
from src.models.myplan import MyPlan
from src.utils import S3, Token, TokenHandler

token_handler = TokenHandler(os.environ["JWT_SECRET"])
security = HTTPBearer()
s3_client = S3(cache_handler=cache_handler)


def get_user_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    return token_handler.decode_token(credentials.credentials)


router = APIRouter(prefix="/content", tags=["Plan"])


class TuneResponse(BaseModel):
    link: str
    link_expiry_at: Optional[datetime]

    class Config:
        json_encoders = {
            datetime: lambda datetime_object: datetime_object.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


@router.get("/plan")
async def get_plan(request: Request, token: Token = Depends(get_user_token)) -> Optional[MyPlan]:
    user_id = token.sub

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


@router.get("/tunes/{tune_type}/{category}/{file_name}")
async def get_tune_link(tune_type: str, category: str, file_name: str):
    path = f"Tunes/{tune_type}/{file_name}"
    # TODO: Yes i know

    link = await s3_client.get_presigned_url(file_name=path)
    expiry_at = await cache_handler.get_key_expiry(key=f"file:{path}")

    if not link:
        raise HTTPException(status_code=502, detail="Unable to generate link")

    return TuneResponse(
        link=link,
        link_expiry_at=expiry_at,
    )


@router.get("/tunes/{tune_type}")
async def get_tune_list(tune_type: str):
    directories = await s3_client.list_files(prefix=f"Tunes/{tune_type}/")
    if not directories:
        raise HTTPException(status_code=404, detail="No tunes found")

    return [directory.split("/")[-1].strip("/") for directory in directories if directory.split("/")[-1].strip("/")]


app.include_router(router)
