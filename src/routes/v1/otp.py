from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from src.utils import EmailHandler

from ..utils import data_handler, get_user_token

router = APIRouter(prefix="/auth/otp", tags=["OTP Authentication"])
email_handler = EmailHandler()


class EmailAddress(BaseModel):
    """Request model containing email address for OTP operations."""

    email_address: str = Field(..., description="User's email address", examples=["user@example.com"])

    model_config = ConfigDict(json_schema_extra={"example": {"email_address": "sarah.johnson@example.com"}})


class OTPRequest(BaseModel):
    """Request model for OTP verification containing email and OTP code."""

    email_address: str = Field(..., description="User's email address", examples=["user@example.com"])
    otp: str = Field(
        ...,
        description="6-digit OTP code",
        examples=["123456"],
        min_length=6,
        max_length=6,
    )

    model_config = ConfigDict(json_schema_extra={"example": {"email_address": "sarah.johnson@example.com", "otp": "123456"}})


@router.post("", dependencies=[Depends(get_user_token)])
async def send_otp(request: Request, data: EmailAddress):
    """
    Send OTP verification code to user's email address.

    Generates and sends a 6-digit one-time password to the user's email
    for account verification purposes. Requires authentication.
    """
    email_address = data.email_address

    user_exists = await data_handler.user_exists(email_address)
    if not user_exists:
        return False

    otp = await data_handler.generate_otp(email_address=email_address)

    await email_handler.send_otp_mail(
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

    user_exists = await data_handler.user_exists(email_address)
    if not user_exists:
        return False

    valid = await data_handler.verify_otp(email_address=email_address, otp=otp)
    if valid:
        await data_handler.verify_user(email_address=email_address)

    return valid
