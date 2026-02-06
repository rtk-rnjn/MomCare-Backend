from __future__ import annotations

import os
import random
import smtplib
import time
import uuid
from email.message import EmailMessage

import bcrypt
import redis
from fastapi import APIRouter, BackgroundTasks, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo.collection import Collection
from pymongo.database import Database

from src.app import app
from src.models import CredentialsDict, CredentialsModel, UserDict, UserModel
from src.routes.api.utils import get_user_id
from src.utils.token_manager import AuthError, TokenManager, TokenPair

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: redis.Redis = app.state.redis_client

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

    def send(self, to: str, subject: str, html: str) -> bool:
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
    email_address: str
    access_token: str
    refresh_token: str

    class Config:
        extra = "ignore"


class ServerMessage(BaseModel):
    detail: str

    class Config:
        extra = "ignore"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _get_credential_by_email(email: str) -> CredentialsDict:
    cred = credentials_collection.find_one({"email_address": email})
    if cred is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return cred


def _get_credential_by_id(user_id: str) -> CredentialsDict:
    cred = credentials_collection.find_one({"_id": user_id})
    if cred is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return cred


def _get_user_or_404(user_id: str) -> UserDict:
    user = users_collection.find_one({"_id": user_id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _json(detail: str, status: int = 200):
    return JSONResponse(content={"detail": detail}, status_code=status)


@router.post("/register", status_code=201, response_model=RegistrationResponse)
def register(data: CredentialsModel = Body(...)):
    if credentials_collection.find_one({"email_address": data.email_address}):
        raise HTTPException(status_code=409, detail="Email address already in use.")

    cred_id = str(uuid.uuid4())
    credentials_collection.insert_one(
        {
            "_id": cred_id,
            "email_address": data.email_address,
            "password": _hash_password(data.password),
        }
    )

    now = time.time()
    users_collection.insert_one(
        {
            "_id": cred_id,
            "created_at_timestamp": now,
            "last_login_timestamp": now,
            "verified_email": False,
        }
    )

    tokens = auth_manager.login(cred_id)
    return RegistrationResponse(email_address=data.email_address, **tokens)


@router.post("/login", response_model=TokenPair)
def login(data: CredentialsModel = Body(...)):
    cred = _get_credential_by_email(data.email_address)
    if not _verify_password(data.password, cred["password"]):
        raise HTTPException(
            status_code=401, detail="Invalid email address or password."
        )

    users_collection.update_one(
        {"_id": cred.get("_id")},
        {"$set": {"last_login_timestamp": time.time()}},
    )

    return auth_manager.login(str(cred.get("_id")))


@router.get("/me", response_model=UserModel)
def get_current_user(user_id: str = Depends(get_user_id)):
    user = users_collection.find_one({"_id": user_id}, {"password": 0})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserModel(**user)  # type: ignore


@router.post("/refresh", response_model=TokenPair)
def refresh_token(refresh_token: str = Body(...)):
    try:
        return auth_manager.refresh(refresh_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")


@router.post("/logout", response_model=ServerMessage)
def logout(refresh_token: str = Body(...)):
    try:
        auth_manager.logout(refresh_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")
    return _json("Logged out successfully.")


@router.patch("/update", response_model=ServerMessage)
def update_user(
    updated_data: UserModel = Body(...),
    user_id: str = Depends(get_user_id),
):
    fields = updated_data.model_dump(exclude_unset=True, by_alias=True)
    fields.pop("id", None)
    fields.pop("_id", None)

    if not fields:
        return _json("No fields to update.")

    result = users_collection.update_one({"_id": user_id}, {"$set": fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found.")

    return _json("User updated successfully.")


@router.delete("/delete", response_model=ServerMessage)
def delete_user(user_id: str = Depends(get_user_id)):
    c = credentials_collection.delete_one({"_id": user_id}).deleted_count
    u = users_collection.delete_one({"_id": user_id}).deleted_count
    if not c and not u:
        raise HTTPException(status_code=404, detail="User not found.")
    return _json("User deleted successfully.")


@router.patch("/change-password", response_model=ServerMessage)
def change_password(
    current_password: str = Body(..., embed=True),
    new_password: str = Body(..., embed=True),
    user_id: str = Depends(get_user_id),
):
    cred = _get_credential_by_id(user_id)
    if not _verify_password(current_password, cred["password"]):
        raise HTTPException(status_code=401, detail="Invalid current password.")

    credentials_collection.update_one(
        {"_id": user_id},
        {"$set": {"password": _hash_password(new_password)}},
    )

    return _json("Password changed successfully.")


@router.post("/request-otp", response_model=ServerMessage)
def request_otp(
    background_tasks: BackgroundTasks,
    email_address: str = Body(..., embed=True),
):
    _get_credential_by_email(email_address)

    otp = str(random.randint(100000, 999999))
    redis_client.setex(f"otp:{email_address}", 600, otp)
    background_tasks.add_task(
        email_handler.send,
        email_address,
        "Your MomCare OTP",
        OTP_CONTENT.format(otp=otp),
    )

    return _json("OTP sent successfully.")


@router.post("/verify-otp", response_model=ServerMessage)
def verify_otp(
    email_address: str = Body(..., embed=True),
    otp: str = Body(..., embed=True),
):
    cred = _get_credential_by_email(email_address)
    stored = redis_client.get(f"otp:{email_address}")

    if stored is None or stored != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    users_collection.update_one(
        {"_id": cred.get("_id")},
        {"$set": {"verified_email": True}},
    )

    return _json("OTP verified successfully.")
