from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from pymongo import UpdateOne

from src.app import app, cache_handler, token_handler
from src.models import PartialUser, User, UserMedical
from src.utils import Token


class ServerResponse(BaseModel):
    """
    Standard server response for authentication operations.
    
    Returns success status, user identifier, and access token for client authentication.
    """
    success: bool = Field(default=True, description="Whether the operation was successful")
    inserted_id: str = Field(..., description="Unique identifier of the user", examples=["user_123456789"])
    access_token: str = Field(..., description="JWT access token for authenticated requests", examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."])

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "inserted_id": "user_123456789",
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzEyMzQ1Njc4OSIsImV4cCI6MTY0MjY4MDAwMH0.signature"
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
                "password": "securePassword123"
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

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "modified_count": 1,
                "matched_count": 1
            }
        }
    )


router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Extract and validate JWT token from Authorization header.
    
    Args:
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        Token: Decoded token information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = token_handler.decode_token(credentials.credentials)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token


@router.post("/register", response_model=ServerResponse)
async def register_user(request: Request, user: User) -> ServerResponse:
    """
    Register a new user account in the MomCare system.
    
    Creates a new user with the provided information, validates email uniqueness,
    and returns an access token for immediate authentication.
    
    Args:
        request: HTTP request object for IP tracking
        user: Complete user registration data
        
    Returns:
        ServerResponse: Success status, user ID, and access token
        
    Raises:
        HTTPException: If user already exists (400)
        
    Example:
        ```python
        # Register a new user
        user_data = {
            "id": "user_123456789",
            "first_name": "Sarah",
            "last_name": "Johnson", 
            "email_address": "sarah@example.com",
            "password": "securePassword123"
        }
        response = await register_user(request, user_data)
        ```
    """
    _user = await cache_handler.user_exists(email_address=user.email_address)
    if _user:
        raise HTTPException(status_code=400, detail="User already exists")

    current_time = datetime.now(timezone.utc)
    user.created_at = current_time
    user.updated_at = current_time
    user.last_login = current_time

    sendable = user.model_dump()
    sendable["_id"] = str(user.id)
    sendable["last_login_ip"] = request.client.host if request.client is not None else "unknown"

    await cache_handler.create_user(user=sendable)

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
    
    Args:
        request: HTTP request object for IP tracking
        credentials: User email and password
        
    Returns:
        ServerResponse: Success status, user ID, and access token
        
    Raises:
        HTTPException: If credentials are invalid (400)
        
    Example:
        ```python
        # Login with credentials
        login_data = {
            "email_address": "sarah@example.com",
            "password": "securePassword123"
        }
        response = await login_user(request, login_data)
        access_token = response.access_token
        ```
    """
    user = await cache_handler.get_user(email=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    current_time = datetime.now(timezone.utc)

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
    """
    Refresh user access token.
    
    Generate a new access token using existing credentials without requiring re-login.
    Useful for maintaining session continuity in client applications.
    
    Args:
        credentials: User email and password for verification
        
    Returns:
        ServerResponse: Success status, user ID, and new access token
        
    Raises:
        HTTPException: If credentials are invalid (400)
        
    Example:
        ```python
        # Refresh token
        refresh_data = {
            "email_address": "sarah@example.com", 
            "password": "securePassword123"
        }
        response = await refresh_token(refresh_data)
        new_token = response.access_token
        ```
    """
    user = await cache_handler.get_user(email=credentials.email_address, password=credentials.password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    new_access_token = token_handler.create_access_token(user)
    return ServerResponse(
        success=True,
        inserted_id=user.id,
        access_token=new_access_token,
    )


@router.post("/update/medical-data", response_model=UpdateResponse)
async def update_medical_data(user_medical_data: dict, token: Token = Depends(get_user_token)):
    """
    Update user's medical and health information.
    
    Allows users to add or modify their medical data including health metrics,
    pre-existing conditions, dietary preferences, and pregnancy information.
    
    Args:
        user_medical_data: Medical information dictionary
        token: Authenticated user token
        
    Returns:
        UpdateResponse: Update operation results
        
    Raises:
        HTTPException: If user not found (404)
        
    Example:
        ```python
        # Update medical data
        medical_data = {
            "date_of_birth": "1990-05-15T00:00:00Z",
            "height": 165.0,
            "pre_pregnancy_weight": 65.0,
            "current_weight": 70.0,
            "dietary_preferences": ["vegetarian"]
        }
        response = await update_medical_data(medical_data, token)
        ```
    """
    user_id = token.sub

    user = await cache_handler.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.medical_data = UserMedical(**user_medical_data)
    await cache_handler.update_user(user_id=user_id, updated_user=user)

    return UpdateResponse(
        success=True,
        modified_count=1,
        matched_count=1,
    )


@router.post("/update", response_model=UpdateResponse)
async def update_user(user_data: dict, token: Token = Depends(get_user_token)) -> UpdateResponse:
    """
    Update user profile information.
    
    Allows modification of user's personal information such as name, contact details,
    and preferences. Validates user ID to ensure data integrity.
    
    Args:
        user_data: Dictionary containing user fields to update
        token: Authenticated user token
        
    Returns:
        UpdateResponse: Update operation results
        
    Raises:
        HTTPException: If user not found (404)
        AssertionError: If user ID mismatch detected
        
    Example:
        ```python
        # Update user profile
        update_data = {
            "id": "user_123456789",
            "first_name": "Sarah",
            "last_name": "Johnson-Smith",
            "phone_number": "+1234567890"
        }
        response = await update_user(update_data, token)
        ```
    """
    user_id = token.sub

    assert user_id == (user_data.get("id") or user_data.get("_id")), "User ID mismatch"

    user = await cache_handler.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _new_user = PartialUser(**user_data)

    await cache_handler.update_user(user_id=user_id, updated_user=_new_user)

    return UpdateResponse(
        success=True,
        modified_count=1,
        matched_count=1,
    )


@router.get("/fetch", response_model=User)
async def fetch_user(token: Token = Depends(get_user_token)) -> User:
    """
    Retrieve complete user profile information.
    
    Returns the authenticated user's complete profile including personal information,
    medical data, exercise history, meal plans, and activity tracking.
    
    Args:
        token: Authenticated user token
        
    Returns:
        User: Complete user profile data
        
    Raises:
        HTTPException: If user not found (404)
        
    Example:
        ```python
        # Fetch user profile
        user_profile = await fetch_user(token)
        print(f"Welcome {user_profile.first_name}!")
        ```
    """
    user_id = token.sub

    user = await cache_handler.get_user(user_id=user_id, force=True)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


app.include_router(router)
