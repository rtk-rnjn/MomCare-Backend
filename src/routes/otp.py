from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

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
    is_verified: bool


class EmailAddress(BaseModel):
    email_address: str


class OTPRequest(BaseModel):
    email_address: str
    otp: str


@router.post("", dependencies=[Depends(get_user_token)])
async def send_otp(request: Request, data: EmailAddress):
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
