from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from src.app import app, cache_handler, token_handler
from src.utils import send_otp_mail

router = APIRouter(prefix="/auth/otp", tags=["OTP Authentication"])
security = HTTPBearer()


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = token_handler.decode_token(credentials.credentials)

    if token is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token


class StatusUpdate(BaseModel):
    """Update model for user verification status."""

    is_verified: bool = Field(..., description="User verification status")

    model_config = ConfigDict(json_schema_extra={"example": {"is_verified": True}})


class EmailAddress(BaseModel):
    """Request model containing email address for OTP operations."""

    email_address: str = Field(..., description="User's email address", examples=["user@example.com"])

    model_config = ConfigDict(json_schema_extra={"example": {"email_address": "sarah.johnson@example.com"}})


class OTPRequest(BaseModel):
    """Request model for OTP verification containing email and OTP code."""

    email_address: str = Field(..., description="User's email address", examples=["user@example.com"])
    otp: str = Field(..., description="6-digit OTP code", examples=["123456"], min_length=6, max_length=6)

    model_config = ConfigDict(json_schema_extra={"example": {"email_address": "sarah.johnson@example.com", "otp": "123456"}})


@router.post("", dependencies=[Depends(get_user_token)])
async def send_otp(request: Request, data: EmailAddress):
    """
    Send OTP verification code to user's email address.

    Generates and sends a 6-digit one-time password to the user's email
    for account verification purposes. Requires authentication.
    """
    email_address = data.email_address

    _user = await cache_handler.user_exists(email_address=email_address)
    if not _user:
        return False

    otp = await cache_handler.generate_otp(email_address=email_address)

    await send_otp_mail(
        email_address=email_address,
        otp=otp,
    )

    return True


@router.post("/verify", dependencies=[Depends(get_user_token)])
async def verify_otp(
    request: Request,
    data: OTPRequest,
):
    """
    Verify OTP code and update user verification status.

    Validates the provided OTP code against the generated code and marks
    the user's account as verified upon successful validation.
    """
    email_address = data.email_address
    otp = data.otp

    _user = await cache_handler.user_exists(email_address=email_address)
    if not _user:
        return False

    if not await cache_handler.verify_otp(email_address=email_address, otp=otp):
        return False

    await cache_handler.update_user(email_address=email_address, updated_user=StatusUpdate(is_verified=True))

    return True


app.include_router(router)
