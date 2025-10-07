from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from src.app import app, token_handler
from src.models import User
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
        ..., description="JWT access token for authenticated requests", examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...signature"]
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


class ClientRequest(BaseModel):
    """
    Client authentication request containing user credentials.

    Used for login and token refresh operations.
    """

    email_address: str = Field(..., description="User's email address", examples=["user@example.com"])
    password: str = Field(..., description="User's password", examples=["securePassword123"])

    model_config = ConfigDict(
        json_schema_extra={"example": {"email_address": "sarah.johnson@example.com", "password": "securePassword123"}}
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


@router.post("/register", response_model=ServerResponse)
async def register_user(request: Request, user: User) -> ServerResponse:
    """
    Register a new user account in the MomCare system.

    Creates a new user with the provided information, validates email uniqueness,
    and returns an access token for immediate authentication.
    """
    user_exists = await data_handler.user_exists(email_address=user.email_address)
    if user_exists:
        raise HTTPException(status_code=400, detail="User already exists")

    current_time = datetime.now(timezone.utc)
    user.created_at = current_time
    user.updated_at = current_time
    user.last_login = current_time
    user.last_login_ip = request.client.host if request.client is not None else "unknown"

    await data_handler.create_user(user)

    return ServerResponse(
        success=True,
        inserted_id=user.id,
        access_token=token_handler.create_access_token(user),
    )


@router.post("/login", response_model=ServerResponse)
async def login_user(request: Request, credentials: ClientRequest) -> ServerResponse:
    """
    Authenticate user and provide access token.

    Validates user credentials and returns authentication token for API access.
    Updates last login timestamp and IP address for security tracking.
    """
    user = await data_handler.get_user(email=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    await data_handler.update_login_meta(
        email_address=credentials.email_address,
        password=credentials.password,
        last_login_ip=request.client.host if request.client is not None else "unknown",
    )

    return ServerResponse(
        success=True,
        inserted_id=user.id,
        access_token=token_handler.create_access_token(user),
    )


@router.post("/refresh", response_model=ServerResponse)
async def refresh_token(credentials: ClientRequest) -> ServerResponse:
    """
    Refresh user access token.

    Generate a new access token using existing credentials without requiring re-login.
    Useful for maintaining session continuity in client applications.
    """
    user = await data_handler.get_user(email=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    new_access_token = token_handler.create_access_token(user)
    return ServerResponse(
        success=True,
        inserted_id=user.id,
        access_token=new_access_token,
    )


@router.get("/fetch", response_model=User)
async def fetch_user(token: Token = Depends(get_user_token)) -> User:
    """
    Retrieve complete user profile information.

    Returns the authenticated user's complete profile including personal information,
    medical data, exercise history, meal plans, and activity tracking.
    """
    user_id = token.sub

    user = await data_handler.get_user_by_id(user_id=user_id, force=True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user
