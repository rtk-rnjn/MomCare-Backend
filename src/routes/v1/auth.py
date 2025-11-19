from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from src.app import token_handler
from src.models.user import UserDict as User
from src.utils import Token

from ..utils import data_handler, get_user_token


class ServerResponse(BaseModel):
    """
    Standard server response for authentication operations.

    Returns success status, user identifier, and access token for client authentication.
    """

    success: bool = Field(default=True, description="Whether the operation was successful")
    inserted_id: str = Field(..., description="Unique identifier of the user", examples=["user_123456789"])
    access_token: str = Field(
        ...,
        description="JWT access token for authenticated requests",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...signature"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "inserted_id": "user_123456789",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMzQ1Njc4OSIsImV4cCI6MTY0MjY4MDAwMH0.signature",  # noqa: E501
            }
        }
    )


class TokenResponse(BaseModel):
    """
    Response model for token-related operations.

    Provides the generated access token for client authentication.
    """

    access_token: str = Field(
        ...,
        description="JWT access token for authenticated requests",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...signature"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMzQ1Njc4OSIsImV4cCI6MTY0MjY4MDAwMH0.signature",  # noqa: E501
            }
        }
    )


class ClientRequest(BaseModel):
    """
    Client authentication request containing user credentials.

    Used for login and token refresh operations.
    """

    email_address: str = Field(..., description="User's email address", examples=["user@example.com"])
    password: str = Field(..., description="User's password", examples=["securePassword123"])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email_address": "sarah.johnson@example.com",
                "password": "securePassword123",
            }
        }
    )


class UpdateResponse(BaseModel):
    """
    Response for update operations indicating the number of records affected.

    Provides feedback on database modification operations.
    """

    success: bool = Field(default=True, description="Whether the update was successful")
    modified_count: int = Field(..., description="Number of records modified", examples=[1])
    matched_count: int = Field(..., description="Number of records matched by the query", examples=[1])

    model_config = ConfigDict(json_schema_extra={"example": {"success": True, "modified_count": 1, "matched_count": 1}})


router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


@router.post("/register")
async def register_user(user: dict):
    """
    Register a new user account in the MomCare system.

    Creates a new user with the provided information, validates email uniqueness,
    and returns an access token for immediate authentication.
    """
    email_address = user.pop("email_address", None)
    password = user.pop("password", None)
    first_name = user.pop("first_name", None)

    if not email_address or not password or not first_name:
        raise HTTPException(status_code=400, detail="Missing required fields: email_address, password, first_name")

    user_data = User(
        email_address=email_address,
        password=password,
        first_name=first_name,
        **user,
    )
    user_data["id"] = f"{uuid.uuid4().hex}"
    user_data["is_verified"] = False
    user_data["created_at_timestamp"] = datetime.now(tz=timezone.utc).timestamp()

    user_exists = await data_handler.user_exists(user_data["email_address"])  # type: ignore
    if user_exists:
        raise HTTPException(status_code=400, detail="User already exists")

    await data_handler.create_user(**user_data)

    return ServerResponse(
        success=True,
        inserted_id=user_data["id"],
        access_token=token_handler.create_access_token(user_data),
    )


@router.post("/login")
async def login_user(credentials: ClientRequest) -> TokenResponse:
    """
    Authenticate user and provide access token.

    Validates user credentials and returns authentication token for API access.
    Updates last login timestamp and IP address for security tracking.
    """
    user = await data_handler.get_user(email_address=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    return TokenResponse(
        access_token=token_handler.create_access_token(user),
    )


@router.post("/refresh")
async def refresh_token(token: Token = Depends(get_user_token)) -> TokenResponse:
    """
    Refresh user access token.

    Generate a new access token using existing credentials without requiring re-login.
    Useful for maintaining session continuity in client applications.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    new_access_token = token_handler.create_access_token(user)
    return TokenResponse(access_token=new_access_token)


@router.get("/fetch-user")
async def fetch_user(token: Token = Depends(get_user_token)):
    """
    Retrieve complete user profile information.

    Returns the authenticated user's complete profile including personal information,
    medical data, exercise history, meal plans, and activity tracking.
    """
    user_id = token.sub

    user = await data_handler.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.post("/update-user")
async def update_user(payload: dict, token: Token = Depends(get_user_token)) -> UpdateResponse:
    """
    Update user profile information.

    Allows modification of user details such as personal info, medical data,
    exercise routines, meal plans, and activity tracking.
    """
    user = await data_handler.get_user_by_id(token.sub)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user = user | payload

    try:
        result = await data_handler.update_user(token.sub, payload=user)

        return UpdateResponse(
            success=result.modified_count > 0, modified_count=result.modified_count, matched_count=result.matched_count
        )
    except ValueError as e:
        print(e)
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/delete-user")
async def delete_user(token: Token = Depends(get_user_token)):
    """
    Delete user account from the MomCare system.

    Permanently removes the user's profile and associated data from the database.
    """
    delete_result = await data_handler.users_collection.delete_one({"id": token.sub})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"success": True, "deleted_count": delete_result.deleted_count}
