from __future__ import annotations

import json
import os
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel

from src.app import app, cache_handler
from src.models import User
from src.utils import TokenHandler, log

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


ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


def get_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = token_handler.decode_token(credentials.credentials)
        if token and token.sub != ADMIN_EMAIL:
            raise HTTPException(status_code=403, detail="Access denied")
        return token
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


async def stream_data(
    *,
    collection: AsyncIOMotorCollection,
    limit: int,
    offset: int = 0,
    sort_by: SortBy = SortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESCENDING,
):
    sort_order_value = 1 if sort_order == SortOrder.ASCENDING else -1

    cursor = collection.find().sort(sort_by.value, sort_order_value).limit(limit).skip(offset)

    async def data_generator():
        async for data in cursor:
            data["id"] = str(data.pop("_id", None))
            yield json.dumps(data) + "\n"

    return StreamingResponse(data_generator(), media_type="application/json")


@router.post("/login")
async def login(request: Request, credentials: Credentials):
    if credentials.email_address != ADMIN_EMAIL or credentials.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Access denied")

    user = User(
        id=ADMIN_EMAIL,
        first_name="MomCare",
        last_name="Admin",
        email_address=ADMIN_EMAIL,
        password=ADMIN_PASSWORD,
    )
    token = token_handler.create_access_token(user)

    return {"token": token}


@router.get("/users", dependencies=[Depends(get_admin_token)])
async def get_all_users(
    limit: int = 10,
    offset: int = 0,
    sort_by: SortBy = SortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESCENDING,
):
    collection: AsyncIOMotorCollection = cache_handler.users_collection
    return await stream_data(
        collection=collection,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/users/search", dependencies=[Depends(get_admin_token)])
async def search_user_by_email(email_address: str):
    collection: AsyncIOMotorCollection = cache_handler.users_collection
    query = {"email_address": {"$regex": email_address, "$options": "i"}}

    return await collection.find_one(query)


@router.get("/users/metadata")
async def get_users_collection_metadata():
    collection = cache_handler.users_collection
    documents = await collection.count_documents({})
    size = await collection.estimated_document_count()
    name = collection.name

    return {"documents": documents, "size": size, "name": name}


@router.get("/foods", dependencies=[Depends(get_admin_token)])
async def get_all_foods(
    limit: int = 10,
    offset: int = 0,
    sort_by: SortBy = SortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESCENDING,
):
    collection: AsyncIOMotorCollection = cache_handler.foods_collection
    return await stream_data(
        collection=collection,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/foods/metadata")
async def get_foods_collection_metadata():
    collection = cache_handler.foods_collection
    documents = await collection.count_documents({})
    size = await collection.estimated_document_count()

    name = collection.name
    return {"documents": documents, "size": size, "name": name}


@router.get("/logs", dependencies=[Depends(get_admin_token)])
async def get_logs():
    return log.log.recent_logs


app.include_router(router, include_in_schema=False)
