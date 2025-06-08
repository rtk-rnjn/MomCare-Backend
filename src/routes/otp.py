from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pymongo import UpdateOne

from src.app import app, cache_handler, token_handler
from src.models import User
from src.utils import Token, send_otp_mail


router = APIRouter(prefix="/auth/otp", tags=["Authentication"])
security = HTTPBearer()


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    return token_handler.decode_token(credentials.credentials)

@router.post("")
async def send_otp(request: Request, email_address: str):
    _user = await cache_handler.user_exists(email_address=email_address)
    if not _user:
        raise HTTPException(status_code=404, detail="User not found")

    otp = await cache_handler.generate_otp(email_address=email_address)

    await send_otp_mail(
        email_address=email_address,
        otp=otp,
    )


@router.post("/verify")
async def verify_otp(
    request: Request,
    email_address: str,
    otp: str,
    token: Token = Depends(get_user_token)
):
    _user = await cache_handler.user_exists(email_address=email_address)
    if not _user:
        raise HTTPException(status_code=404, detail="User not found")

    if not await cache_handler.verify_otp(email_address=email_address, otp=otp):
        return False

    # Update the user's last login time
    await cache_handler.update_user(
        user_id=token.sub,
        updated_user=BaseModel(is_verified=True)
    )

    return True
