from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.app import app, database, limiter
from src.models import User
from src.utils import TokenHandler

if TYPE_CHECKING:
    pass


class ServerResponse(BaseModel):
    success: bool = True
    inserted_id: str
    access_token: str


class ClientRequest(BaseModel):
    email_address: str
    password: str


router = APIRouter(prefix="/auth", tags=["Authentication"])
token_handler = TokenHandler(os.environ["JWT_SECRET"])
__cached_emails = set()


@router.post("/register", response_model=ServerResponse)
@limiter.limit("15/minute")
async def register_user(request: Request, user: User) -> ServerResponse:
    _user = await database["users"].find_one({"email_address": user.email_address})
    if _user or user.email_address in __cached_emails:
        raise HTTPException(status_code=400, detail="User already exists")

    current_time = datetime.now(timezone.utc)
    user.created_at = current_time
    user.updated_at = current_time
    user.last_login = current_time
    user.failed_login_attempts = 0

    sendable = user.model_dump(mode="json")
    sendable["_id"] = str(user.id)
    sendable["last_login_ip"] = (
        request.client.host if request.client is not None else "unknown"
    )

    await database["users"].insert_one(sendable)

    __cached_emails.add(user.email_address)

    return ServerResponse(
        success=True,
        inserted_id=str(user.id),
        access_token=token_handler.create_access_token(user),
    )


@router.post("/login", response_model=ServerResponse)
@limiter.limit("15/minute")
async def login_user(request: Request, credentials: ClientRequest) -> ServerResponse:
    user = await database["users"].find_one(
        {"email_address": credentials.email_address}
    )
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    if user["password"] != credentials.password:
        await database["users"].update_one(
            {"email_address": credentials.email_address},
            {"$inc": {"failed_login_attempts": 1}},
        )
        user["failed_login_attempts"] += 1
        raise HTTPException(status_code=400, detail="Invalid password")

    current_time = datetime.now(timezone.utc)
    user["last_login"] = current_time
    user["last_login_ip"] = (
        request.client.host if request.client is not None else "unknown"
    )

    await database["users"].update_one(
        {
            "email_address": credentials.email_address,
            "password": credentials.password,
        },
        {
            "$set": {
                "last_login": current_time,
                "last_login_ip": (
                    request.client.host if request.client is not None else "unknown"
                ),
            }
        },
    )
    __cached_emails.add(user["email_address"])
    return ServerResponse(
        success=True,
        inserted_id=str(user["_id"]),
        access_token=token_handler.create_access_token(User(**user)),
    )


@router.post("/refresh", response_model=ServerResponse)
# @limiter.limit("1/hour")
async def refresh_token(request: Request, credentials: ClientRequest) -> ServerResponse:
    user = await database["users"].find_one(
        {"email_address": credentials.email_address, "password": credentials.password}
    )
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    new_access_token = token_handler.create_access_token(User(**user))
    return ServerResponse(
        success=True,
        inserted_id=str(user["_id"]),
        access_token=new_access_token,
    )


app.include_router(router)
