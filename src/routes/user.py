from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from pymongo.results import InsertOneResult

from src.app import app, mongo_client
from src.models import User
from type import UpdateResult

__all__ = ("create_user", "update_user", "fetch_user")

router = APIRouter(prefix="/user", tags=["User"])


class CreateResponse(BaseModel):
    success: bool
    inserted_id: str


class UpdateResponse(BaseModel):
    success: bool
    modified_count: int
    detail: Optional[str] = None


async def _fetch_user(*, email: str, password: str) -> User:
    collection = mongo_client["MomCare"]["users"]
    user = await collection.find_one({"email_address": email, "password": password})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return User.model_validate(user)


async def user_exists(*, email: str) -> bool:
    collection = mongo_client["MomCare"]["users"]
    return await collection.count_documents({"email_address": email}) > 0


@router.post(
    "/create",
    response_model=CreateResponse,
    responses={400: {"description": "User already exists"}, 422: {}},
)
async def create_user(request: Request, data: dict) -> CreateResponse:
    """
    Create a new user and return the inserted ID.
    """
    print(data)
    data = User(**data)
    if await user_exists(email=data.email_address):
        return CreateResponse(success=False, inserted_id="")

    collection = mongo_client["MomCare"]["users"]
    sendable_data = data.model_dump(mode="json")
    sendable_data["_id"] = sendable_data.pop("id")

    result: InsertOneResult = await collection.insert_one(sendable_data)

    response = {"success": True, "inserted_id": str(result.inserted_id)}
    return CreateResponse(**response)


@router.get(
    "/fetch",
    response_model=User,
    responses={404: {"description": "User not found"}, 422: {}},
)
async def fetch_user(request: Request, email: EmailStr, password: str) -> User:
    """
    Fetch user details using email and password.
    """
    return await _fetch_user(email=email, password=password)


@router.get(
    "/fetch/{_id}",
    response_model=User,
    responses={404: {"description": "User not found"}, 422: {}},
)
async def fetch_user_by_id(request: Request, _id: str) -> User:
    """
    Fetch user details using the user ID.
    """
    collection = mongo_client["MomCare"]["users"]
    user = await collection.find_one({"_id": _id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return User.model_validate(user)


@router.put(
    "/update/{_id}",
    response_model=UpdateResponse,
    responses={
        400: {"description": "Invalid update operation"},
        404: {"description": "User not found"},
        422: {},
    },
)
async def update_user(request: Request, user: User) -> UpdateResponse:
    """
    Update user details based on the user ID.
    """
    collection = mongo_client["MomCare"]["users"]
    try:
        user_dumped = user.model_dump(mode="json")
        print(user_dumped)
        result: UpdateResult = await collection.update_one(
            {"_id": user.id},
            {"$set": user_dumped},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="User not found")

    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid update operation")

    return UpdateResponse(success=True, modified_count=result.modified_count)


app.include_router(router)
