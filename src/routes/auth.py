from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pymongo import InsertOne, UpdateOne

from src.app import app, cache_handler, database
from src.models import User
from src.utils import Token, TokenHandler

if TYPE_CHECKING:

    from type import UpdateResult


class ServerResponse(BaseModel):
    success: bool = True
    inserted_id: str
    access_token: str


class ClientRequest(BaseModel):
    email_address: str
    password: str


class UpdateResponse(BaseModel):
    success: bool = True
    modified_count: int
    matched_count: int


router = APIRouter(prefix="/auth", tags=["Authentication"])
token_handler = TokenHandler(os.environ["JWT_SECRET"])
security = HTTPBearer()


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return token_handler.decode_token(credentials.credentials)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


@router.post("/register", response_model=ServerResponse)
async def register_user(request: Request, user: User) -> ServerResponse:
    _user = await cache_handler.get_user(user.id)
    if _user:
        raise HTTPException(status_code=400, detail="User already exists")

    current_time = datetime.now(timezone.utc)
    user.created_at = current_time
    user.updated_at = current_time
    user.last_login = current_time

    sendable = user.model_dump(mode="json")
    sendable["_id"] = str(user.id)
    sendable["last_login_ip"] = request.client.host if request.client is not None else "unknown"

    await cache_handler.users_collection_operations.put(InsertOne(sendable))
    await cache_handler.set_user(user=user)

    return ServerResponse(
        success=True,
        inserted_id=str(user.id),
        access_token=token_handler.create_access_token(user),
    )


@router.post("/login", response_model=ServerResponse)
async def login_user(request: Request, credentials: ClientRequest) -> ServerResponse:
    user = await cache_handler.get_user(email=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    current_time = datetime.now(timezone.utc).isoformat()

    await cache_handler.users_collection_operations.put(
        UpdateOne(
            {
                "email_address": credentials.email_address,
                "password": credentials.password,
            },
            {
                "$set": {
                    "last_login": current_time,
                    "last_login_ip": (request.client.host if request.client is not None else "unknown"),
                }
            },
        )
    )

    return ServerResponse(
        success=True,
        inserted_id=user.id,
        access_token=token_handler.create_access_token(user),
    )


@router.post("/refresh", response_model=ServerResponse)
async def refresh_token(credentials: ClientRequest) -> ServerResponse:
    user = await cache_handler.get_user(email=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    new_access_token = token_handler.create_access_token(user)
    return ServerResponse(
        success=True,
        inserted_id=user.id,
        access_token=new_access_token,
    )


@router.post("/update", response_model=UpdateResponse)
async def update_user(user_data: dict, token: Token = Depends(get_user_token)) -> UpdateResponse:
    user_id = token.sub

    user_data.pop("id", None)
    user_data.pop("created_at", None)
    user_data.pop("_id", None)

    await cache_handler.users_collection_operations.put(
        UpdateOne(
            {"_id": user_id},
            {"$set": user_data},
        )
    )

    return UpdateResponse(
        success=True,
        modified_count=1,
        matched_count=1,
    )


@router.get("/fetch", response_model=User)
async def fetch_user(token: Token = Depends(get_user_token)) -> User:
    user_id = token.sub

    user = await cache_handler.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


app.include_router(router)
