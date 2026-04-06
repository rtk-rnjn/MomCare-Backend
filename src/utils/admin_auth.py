from __future__ import annotations

import os
import time

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from redis.asyncio import Redis

from src.app import app

_SECRET = os.environ["SESSION_SECRET_KEY"]
_CSRF_SERIALIZER = URLSafeTimedSerializer(_SECRET, salt="csrf-token")

ADMIN_LOGIN_RATE_LIMIT = int(os.getenv("ADMIN_LOGIN_RATE_LIMIT", "10"))
ADMIN_LOGIN_RATE_WINDOW = int(os.getenv("ADMIN_LOGIN_RATE_WINDOW", "300"))

ADMIN_ALLOWED_IPS_RAW = os.getenv("ADMIN_ALLOWED_IPS", "").strip()
ADMIN_ALLOWED_IPS: list[str] = [ip.strip() for ip in ADMIN_ALLOWED_IPS_RAW.split(",") if ip.strip()] if ADMIN_ALLOWED_IPS_RAW else []

redis_client: Redis = app.state.redis_client


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def check_ip_allowlist(request: Request) -> None:
    if not ADMIN_ALLOWED_IPS:
        return
    client_ip = get_client_ip(request)
    if client_ip not in ADMIN_ALLOWED_IPS:
        raise HTTPException(status_code=403, detail="Access denied: IP not in allowlist.")


async def check_login_rate_limit(request: Request) -> None:
    ip = get_client_ip(request)
    key = f"admin:login_attempts:{ip}"
    now = time.time()
    window_start = now - ADMIN_LOGIN_RATE_WINDOW

    async with redis_client.pipeline(transaction=True) as pipe:
        await pipe.zremrangebyscore(key, 0, window_start)
        await pipe.zadd(key, {str(now): now})
        await pipe.zcard(key)
        await pipe.ttl(key)
        _, _, count, ttl = await pipe.execute()

    if ttl == -1:
        await redis_client.expire(key, ADMIN_LOGIN_RATE_WINDOW)

    if count > ADMIN_LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Too many login attempts. Please wait {ADMIN_LOGIN_RATE_WINDOW // 60} minutes.",
            headers={
                "X-RateLimit-Limit": str(ADMIN_LOGIN_RATE_LIMIT),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(now + ADMIN_LOGIN_RATE_WINDOW)),
                "Retry-After": str(ADMIN_LOGIN_RATE_WINDOW),
            },
        )


def generate_csrf_token(session_id: str) -> str:
    return _CSRF_SERIALIZER.dumps(session_id)


def validate_csrf_token(token: str, session_id: str, max_age: int = 3600) -> bool:
    try:
        value = _CSRF_SERIALIZER.loads(token, max_age=max_age)
        return value == session_id
    except (BadSignature, SignatureExpired):
        return False


def require_csrf(request: Request) -> None:
    session_id = request.session.get("admin_session_id")
    if not session_id:
        raise HTTPException(status_code=403, detail="CSRF: no session.")

    token = request.headers.get("X-CSRF-Token") or request.cookies.get("csrf_token")
    if not token:
        raise HTTPException(status_code=403, detail="CSRF token missing.")

    if not validate_csrf_token(token, session_id):
        raise HTTPException(status_code=403, detail="CSRF token invalid or expired.")


def get_admin_session(request: Request) -> dict:
    session = request.session
    if not session.get("admin_logged_in"):
        raise HTTPException(
            status_code=303,
            detail="Redirecting to login",
            headers={"Location": str(request.url_for("admin_login_get"))},
        )
    return session


def mask_sensitive_fields(data: dict, fields: set[str] | None = None) -> dict:
    if fields is None:
        fields = {"password_hash", "password", "secret", "token", "apple_id"}

    result = {}
    for key, value in data.items():
        if key in fields:
            result[key] = "***MASKED***"
        elif isinstance(value, dict):
            result[key] = mask_sensitive_fields(value, fields)
        else:
            result[key] = value
    return result
