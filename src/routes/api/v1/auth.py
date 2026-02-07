from __future__ import annotations

import inspect
import random
import uuid
from typing import TYPE_CHECKING

import arrow
import bcrypt
from fastapi import APIRouter, BackgroundTasks, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis

from src.app import app
from src.models import CredentialsDict, CredentialsModel, UserDict, UserModel
from src.routes.api.utils import get_user_id
from src.utils.email_handler import EmailHandler
from src.utils.token_manager import AuthError, TokenManager, TokenPair

from .objects import RegistrationResponse, ServerMessage

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]


email_handler = EmailHandler()


def _hash_password(password: str, /) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(*, password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def _get_credential_by_email(email: str, /) -> CredentialsDict:
    cred = await credentials_collection.find_one({"email_address": email})
    if cred is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return cred


async def _get_credential_by_id(user_id: str, /) -> CredentialsDict:
    cred = await credentials_collection.find_one({"_id": user_id})
    if cred is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return cred


def _create_json_response(*, detail: str, status: int = 200):
    return JSONResponse(content={"detail": detail}, status_code=status)


@router.post(
    "/register",
    name="Register User",
    status_code=201,
    response_model=RegistrationResponse,
    response_description="The registered email address along with access and refresh tokens for authentication.",
    summary="Register a new user account",
    description="Create a new user account using an email address and password. Returns the registered email address along with access and refresh tokens for authentication.",
    responses={
        201: {"description": "User registered successfully."},
        400: {"description": "Email address and password are required."},
        409: {"description": "Email address already in use."},
        422: {"description": "Validation error."},
    },
)
async def register(data: CredentialsModel = Body(...)):
    if not data.email_address or not data.password:
        raise HTTPException(status_code=400, detail="Email address and password are required.")

    if await credentials_collection.find_one({"email_address": data.email_address}):
        raise HTTPException(status_code=409, detail="Email address already in use.")

    cred_id = str(uuid.uuid4())

    now = arrow.utcnow().timestamp()
    await credentials_collection.insert_one(
        {
            "_id": cred_id,
            "email_address": data.email_address,
            "password": _hash_password(data.password),
            "created_at_timestamp": now,
            "last_login_timestamp": now,
            "verified_email": False,
            "google_id": None,
            "apple_id": None,
        }
    )

    await users_collection.insert_one({"_id": cred_id})

    tokens = auth_manager.login(cred_id)
    return RegistrationResponse(email_address=data.email_address, **tokens)


@router.post(
    "/login",
    name="Login User",
    status_code=200,
    response_model=TokenPair,
    summary="Login to user account",
    description="Authenticate a user using their email address and password. Returns access and refresh tokens for authentication if the credentials are valid.",
    responses={
        200: {"description": "Login successful."},
        400: {"description": "Email address and password are required."},
        401: {"description": "Invalid email address or password."},
        422: {"description": "Validation error."},
    },
)
async def login(data: CredentialsModel = Body(...)):
    if not data.email_address or not data.password:
        raise HTTPException(status_code=400, detail="Email address and password are required.")

    cred = await _get_credential_by_email(data.email_address)

    if TYPE_CHECKING:
        assert "password" in cred

    if not _verify_password(password=data.password, hashed=cred.get("password") or _hash_password("")):
        raise HTTPException(status_code=401, detail="Invalid email address or password.")

    await credentials_collection.update_one(
        {"_id": cred.get("_id")},
        {"$set": {"last_login_timestamp": arrow.utcnow().timestamp()}},
    )

    return auth_manager.login(str(cred.get("_id")))


@router.get(
    "/me",
    name="Get Current User",
    status_code=200,
    response_model=UserModel,
    summary="Get current authenticated user",
    description="Retrieve the details of the currently authenticated user. Requires a valid access token.",
    responses={
        200: {"description": "User details retrieved successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
    },
)
async def get_current_user(user_id: str = Depends(get_user_id)):
    user = await users_collection.find_one({"_id": user_id}, {"password": 0})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserModel(**user)  # type: ignore


@router.post(
    "/refresh",
    name="Refresh Token",
    status_code=200,
    response_model=TokenPair,
    summary="Refresh authentication tokens",
    description="Obtain new access and refresh tokens using a valid refresh token. Returns new tokens if the provided refresh token is valid.",
    responses={
        200: {"description": "Tokens refreshed successfully."},
        401: {"description": "Invalid refresh token."},
        422: {"description": "Validation error."},
    },
)
async def refresh_token(
    refresh_token: str = Body(
        embed=True,
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        description="The refresh token used to obtain new authentication tokens.",
        title="Refresh Token",
        alias="refresh_token",
    ),
):
    try:
        return auth_manager.refresh(refresh_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")


@router.post(
    "/logout",
    name="Logout User",
    status_code=200,
    response_model=ServerMessage,
    summary="Logout user",
    description="Invalidate the provided refresh token to log the user out. Requires a valid refresh token. Returns a message confirming successful logout if the token is valid.",
    responses={
        200: {"description": "Logged out successfully."},
        401: {"description": "Invalid refresh token."},
        422: {"description": "Validation error."},
    },
)
async def logout(
    refresh_token: str = Body(
        embed=True,
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        description="The refresh token to invalidate for logging out.",
        title="Refresh Token",
        alias="refresh_token",
    ),
):
    try:
        auth_manager.logout(refresh_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    return _create_json_response(detail="Logged out successfully.")


@router.patch(
    "/update",
    name="Update User Details",
    status_code=200,
    response_model=ServerMessage,
    summary="Update current user details",
    description="Update the details of the currently authenticated user. Requires a valid access token. Accepts any subset of user fields to update and returns a message confirming successful update.",
    responses={
        200: {"description": "User updated successfully."},
        304: {"description": "No changes made to the user."},
        400: {"description": "No fields to update."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
        422: {"description": "Validation error."},
    },
)
async def update_user(
    updated_data: UserModel = Body(...),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    fields = updated_data.model_dump(exclude_unset=True, by_alias=True)
    fields.pop("id", None)
    fields.pop("_id", None)

    if not fields:
        return _create_json_response(detail="No fields to update.")

    result = await users_collection.update_one({"_id": user_id}, {"$set": fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    if result.modified_count == 0:
        return _create_json_response(detail="No changes made to the user.", status=304)

    return _create_json_response(detail="User updated successfully.")


@router.delete(
    "/delete",
    name="Delete User Account",
    status_code=200,
    response_model=ServerMessage,
    response_description="A message confirming successful deletion of the user account.",
    summary="Delete current user account",
    description="Permanently delete the currently authenticated user's account. Requires a valid access token. Deletes the user's credentials and details from the database and returns a message confirming successful deletion.",
    responses={
        200: {"description": "User deleted successfully."},
        401: {"description": "Unauthorized. Invalid or missing access token."},
        404: {"description": "User not found."},
    },
)
async def delete_user(user_id: str = Depends(get_user_id, use_cache=False)):
    delete_result = await credentials_collection.delete_one({"_id": user_id})
    c = delete_result.deleted_count

    delete_result = await users_collection.delete_one({"_id": user_id})
    u = delete_result.deleted_count

    if not c and not u:
        raise HTTPException(status_code=404, detail="User not found.")

    return _create_json_response(detail="User deleted successfully.")


@router.patch(
    "/change-password",
    response_model=ServerMessage,
    response_description="A message confirming successful password change.",
    name="Change User Password",
    status_code=200,
    summary="Change user password",
    description="Change the password of the currently authenticated user. Requires a valid access token. Accepts the current password and the new password, verifies the current password, and updates to the new password if valid. Returns a message confirming successful password change.",
    responses={
        200: {"description": "Password changed successfully."},
        400: {"description": "Current password and new password are required."},
        401: {"description": "Invalid current password."},
        404: {"description": "User not found."},
        422: {"description": "Validation error."},
    },
)
async def change_password(
    current_password: str = Body(
        embed=True,
        examples=["current_password123"],
        description="The user's current password.",
        title="Current Password",
        alias="current_password",
    ),
    new_password: str = Body(
        embed=True, examples=["new_password123"], description="The user's new password.", title="New Password", alias="new_password"
    ),
    user_id: str = Depends(get_user_id),
):
    cred = await _get_credential_by_id(user_id)
    if not _verify_password(password=current_password, hashed=cred.get("password") or _hash_password("")):
        raise HTTPException(status_code=401, detail="Invalid current password.")

    await credentials_collection.update_one(
        {"_id": user_id},
        {"$set": {"password": _hash_password(new_password)}},
    )

    return _create_json_response(detail="Password changed successfully.")


@router.post(
    "/request-otp",
    name="Request OTP for Email Verification",
    status_code=200,
    response_model=ServerMessage,
    response_description="A message confirming that the OTP was sent successfully.",
    summary="Request OTP for email verification",
    description="Request a One-Time Password (OTP) to be sent to the user's email address for verification purposes. Accepts the user's email address and sends an OTP to that address if it exists in the system. Returns a message confirming that the OTP was sent successfully.",
    responses={
        200: {"description": "OTP sent successfully."},
        404: {"description": "User with the provided email address not found."},
        422: {"description": "Validation error."},
    },
)
async def request_otp(
    background_tasks: BackgroundTasks,
    email_address: str = Body(
        embed=True,
        examples=["user@example.com"],
        description="The email address to which the OTP should be sent.",
        title="Email Address",
        alias="email_address",
    ),
):
    await _get_credential_by_email(email_address)
    otp = str(random.randint(100000, 999999))
    await redis_client.setex(f"otp:{email_address}", 600, otp)

    background_tasks.add_task(
        email_handler.send_email,
        to=email_address,
        subject="Your MomCare OTP",
        otp=otp,
    )

    return _create_json_response(detail="OTP sent successfully.")


@router.post(
    "/verify-otp",
    response_model=ServerMessage,
    response_description="A message confirming successful OTP verification.",
    name="Verify OTP for Email Verification",
    status_code=200,
    summary="Verify OTP for email verification",
    description="Verify a One-Time Password (OTP) sent to the user's email address for verification purposes. Accepts the user's email address and the OTP, and verifies the OTP if it matches the one stored in the system. Returns a message confirming successful verification.",
    responses={
        200: {"description": "OTP verified successfully."},
        400: {"description": "Invalid OTP."},
        404: {"description": "User with the provided email address not found."},
        422: {"description": "Validation error."},
    },
)
async def verify_otp(
    email_address: str = Body(
        embed=True,
        examples=["user@example.com"],
        description="The email address associated with the OTP.",
        title="Email Address",
        alias="email_address",
    ),
    otp: str = Body(
        embed=True,
        examples=["123456"],
        description="The OTP to verify.",
        title="OTP",
        alias="otp",
    ),
):
    cred = await _get_credential_by_email(email_address)
    stored = redis_client.get(f"otp:{email_address}")
    if inspect.isawaitable(stored):
        stored = await stored

    if stored is None or stored != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    await credentials_collection.update_one(
        {"_id": cred.get("_id")},
        {"$set": {"verified_email": True}},
    )

    return _create_json_response(detail="OTP verified successfully.")
