from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, TypedDict

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.models.admin import AdminRole

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "")
JWT_ALGO = os.environ.get("JWT_ALGORITHM", "HS256")

ADMIN_ACCESS_EXP = timedelta(hours=2)
ADMIN_REFRESH_EXP = timedelta(days=1)

ISSUER = "momcare-admin"
AUDIENCE = "admin"


class AdminAccessPayload(TypedDict):
    sub: str
    username: str
    role: str
    iss: str
    aud: str
    iat: int
    exp: int
    type: Literal["admin_access"]


class AdminRefreshPayload(TypedDict):
    sub: str
    iss: str
    aud: str
    iat: int
    exp: int
    jti: str
    type: Literal["admin_refresh"]


class AdminTokenPair(TypedDict):
    access_token: str
    refresh_token: str
    expires_at_timestamp: int


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_admin_access_token(admin_id: str, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": admin_id,
        "username": username,
        "role": role,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + ADMIN_ACCESS_EXP,
        "type": "admin_access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def create_admin_refresh_token(admin_id: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": admin_id,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + ADMIN_REFRESH_EXP,
        "jti": jti,
        "type": "admin_refresh",
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return token, jti


def decode_admin_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        decoded = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGO],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=30,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Admin token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid admin token")

    if decoded.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")

    return decoded


admin_security = HTTPBearer()


def get_current_admin(credentials: HTTPAuthorizationCredentials = Depends(admin_security)) -> AdminAccessPayload:
    payload = decode_admin_token(credentials.credentials, "admin_access")
    return AdminAccessPayload(
        sub=payload["sub"],
        username=payload["username"],
        role=payload["role"],
        iss=payload["iss"],
        aud=payload["aud"],
        iat=payload["iat"],
        exp=payload["exp"],
        type="admin_access",
    )


def require_super_admin(admin: AdminAccessPayload = Depends(get_current_admin)) -> AdminAccessPayload:
    if admin["role"] != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super admin privileges required")
    return admin


def require_admin(admin: AdminAccessPayload = Depends(get_current_admin)) -> AdminAccessPayload:
    if admin["role"] not in (AdminRole.SUPER_ADMIN, AdminRole.ADMIN):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return admin


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"
