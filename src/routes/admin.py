from __future__ import annotations

import os
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel

from src.app import app, cache_handler
from src.models import User
from src.utils import Token, TokenHandler

router = APIRouter(prefix="/admin", tags=["Admin"])
token_handler = TokenHandler(os.environ["JWT_SECRET"])
security = HTTPBearer()


class SortBy(str, Enum):
    FIRST_NAME = "first_name"
    LAST_NAME = "last_name"
    EMAIL_ADDRESS = "email_address"
    CREATED_AT = "created_at"


class SortOrder(str, Enum):
    ASCENDING = "asc"
    DESCENDING = "desc"


class Credentials(BaseModel):
    email_address: str
    password: str


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = token_handler.decode_token(credentials.credentials)
        if token and token.sub != "admin@momcare.site":
            raise HTTPException(status_code=403, detail="Access denied")
        return token
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


async def stream_users(
    collection: AsyncIOMotorCollection,
    limit: int,
    sort_by: SortBy = SortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESCENDING,
):
    sort_order_value = 1 if sort_order == SortOrder.ASCENDING else -1

    cursor = collection.find().sort(sort_by.value, sort_order_value).limit(limit)

    async def user_generator():
        async for user in cursor:
            user["id"] = str(user["_id"])
            yield user

    return StreamingResponse(user_generator(), media_type="application/json")


@router.post("/login")
async def login(request: Request, credentials: Credentials):
    if credentials.email_address != "admin@momcare.site":
        raise HTTPException(status_code=403, detail="Access denied")

    user_data = await cache_handler.users_collection.find_one({"email_address": credentials.email_address, "password": credentials.password})
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = User(**user_data)
    token = token_handler.create_access_token(user)

    return {"access_token": token, "token_type": "bearer"}


@router.get("/users")
async def get_all_users(
    request: Request,
    limit: int,
    sort_by: SortBy = SortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESCENDING,
    token: Token = Depends(get_user_token),
):
    collection: AsyncIOMotorCollection = cache_handler.users_collection
    return await stream_users(collection, limit, sort_by, sort_order)


@router.get("/foods")
async def get_all_foods(
    request: Request,
    limit: int,
    sort_by: SortBy = SortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESCENDING,
    token: Token = Depends(get_user_token),
):
    collection: AsyncIOMotorCollection = cache_handler.foods_collection
    return await stream_users(collection, limit, sort_by, sort_order)


@router.get("/users/{user_id}")
async def get_user_by_id(user_id: str, token: Token = Depends(get_user_token)):
    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.get("/foods/{food_id}")
async def get_food_by_id(food_id: str, token: Token = Depends(get_user_token)):
    food = await cache_handler.get_food(food_id)
    if not food:
        raise HTTPException(status_code=404, detail="Food not found")

    return food


app.include_router(router)
