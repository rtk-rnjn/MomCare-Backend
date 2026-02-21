from __future__ import annotations

import time

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis

from src.app import app
from src.utils import AuthError, TokenManager

security = HTTPBearer()
auth_manager: TokenManager = app.state.auth_manager

redis_client: Redis = app.state.redis_client

RATE = 1
WINDOW = 10


async def rate_limiter(request: Request):
    identifier = request.client.host if request.client else "unknown"

    key = f"rate:{identifier}"
    now = time.time()
    window_start = now - WINDOW

    async with redis_client.pipeline(transaction=True) as pipe:
        await pipe.zremrangebyscore(key, 0, window_start)
        await pipe.zadd(key, {str(now): now})
        await pipe.zcard(key)
        await pipe.ttl(key)

        _, _, count, ttl = await pipe.execute()

    if ttl == -1:
        await redis_client.expire(key, WINDOW)

    if count > RATE:
        raise HTTPException(
            status_code=429,
            headers={
                "X-RateLimit-Limit": str(RATE),
                "X-RateLimit-Remaining": str(max(0, RATE - count)),
                "X-RateLimit-Reset": str(int(now + WINDOW)),
            },
        )


ERROR_MAP = {
    "Refresh token revoked": "refresh_token_revoked",
    "Invalid token payload": "invalid_token_payload",
    "Invalid token": "invalid_token",
    "Token expired": "token_expired",
}


def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return auth_manager.authenticate(credentials.credentials)
    except AuthError as e:
        ERROR_MAP.get(str(e), "invalid_token")

        raise HTTPException(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_access_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return auth_manager.decode(credentials.credentials, "access")
    except AuthError as e:
        ERROR_MAP.get(str(e), "invalid_token")

        raise HTTPException(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return auth_manager.decode(credentials.credentials, "refresh")
    except AuthError as e:
        ERROR_MAP.get(str(e), "invalid_token")

        raise HTTPException(
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
