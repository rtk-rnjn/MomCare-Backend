from __future__ import annotations

import inspect
import os
import random
import smtplib
import uuid
from email.message import EmailMessage
from typing import TYPE_CHECKING

import arrow
import bcrypt
from fastapi import APIRouter, BackgroundTasks, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis

from src.app import app
from src.models import CredentialsDict, CredentialsModel, UserDict, UserModel
from src.routes.api.utils import get_user_id
from src.utils.token_manager import AuthError, TokenManager, TokenPair

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]

OTP_CONTENT = """
<!DOCTYPE html>
<html>
    <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
        <div style="max-width: 500px; margin: auto; background-color: #ffffff; padding: 24px;">

            <h2 style="color: #924350; margin-bottom: 16px;">MomCare+</h2>
            <p style="font-size: 16px; color: #000;">
                Your MomCare+ email verification code is:
            </p>
            <p style="font-size: 26px; font-weight: bold; color: #000; margin: 8px 0 20px 0;">
                {otp}
            </p>
            <p style="font-size: 14px; color: #444;">
                This code is valid for 10 minutes. Do not share it with anyone.
            </p>
            <p style="font-size: 14px; color: #666;">
                If you did not request this, you can safely ignore this email.
            </p>

            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
            <p style="font-size: 12px; color: #999;">
                Team MomCare+<br/>
                We will never ask for your verification code.
            </p>
        </div>
    </body>
</html>
"""


class EmailHandler:
    EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
    EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_FROM = "MomCare <no-reply@momcare.com>"

    def send(self, *, to: str, subject: str, html: str) -> bool:
        msg = EmailMessage()
        msg["From"] = self.EMAIL_FROM
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(html, subtype="html")
        try:
            with smtplib.SMTP(self.EMAIL_HOST, self.EMAIL_PORT) as server:
                server.starttls()
                server.login(self.EMAIL_ADDRESS, self.EMAIL_PASSWORD)
                server.send_message(msg)
        except Exception:
            return False
        return True


email_handler = EmailHandler()


class RegistrationResponse(BaseModel):
    email_address: str = Field(..., description="The registered email address.", examples=["user@example.com"])
    access_token: str = Field(
        ...,
        description="The access token for authentication.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    refresh_token: str = Field(
        ...,
        description="The refresh token for obtaining new access tokens.",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )

    class Config:
        extra = "ignore"


class ServerMessage(BaseModel):
    detail: str = Field(
        ...,
        description="A message describing the result of the operation.",
        examples=["User registered successfully."],
    )

    class Config:
        extra = "ignore"


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


@router.patch("/change-password", response_model=ServerMessage)
async def change_password(
    current_password: str = Body(..., embed=True),
    new_password: str = Body(..., embed=True),
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
        email_handler.send,
        to=email_address,
        subject="Your MomCare OTP",
        html=OTP_CONTENT.format(otp=otp),
    )

    return _create_json_response(detail="OTP sent successfully.")


@router.post(
    "/verify-otp",
    response_model=ServerMessage,
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
