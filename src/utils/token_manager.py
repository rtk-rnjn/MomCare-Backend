from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Literal, Mapping, TypedDict, overload

import arrow
import jwt
from dotenv import load_dotenv
from redis.asyncio import Redis

_ = load_dotenv(verbose=True)

JWT_SECRET = os.environ["JWT_SECRET_KEY"]
JWT_ALGO = os.environ["JWT_ALGORITHM"]

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "10"))

ACCESS_EXP = timedelta(minutes=60)
REFRESH_EXP = timedelta(days=7)

ISSUER = "server"
AUDIENCE = "individuals"


class BasePayload(TypedDict):
    sub: str
    iss: str
    aud: str
    iat: datetime


class AccessPayload(BasePayload):
    type: Literal["access"]
    exp: datetime


class RefreshPayload(BasePayload):
    type: Literal["refresh"]
    jti: str
    exp: datetime


class DecodedBasePayload(TypedDict):
    sub: str
    iss: str
    aud: str
    iat: int


class DecodedAccessPayload(DecodedBasePayload):
    type: Literal["access"]
    exp: int


class DecodedRefreshPayload(DecodedBasePayload):
    type: Literal["refresh"]
    jti: str
    exp: int


class TokenPairDict(TypedDict):
    access_token: str
    refresh_token: str
    expires_at_timestamp: float


class AuthError(Exception):
    pass


class SingletonMeta(type):
    _instances = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class TokenManager(metaclass=SingletonMeta):
    def __init__(self):
        self.redis_client = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )

    def utc_now(self):
        return arrow.utcnow().datetime

    def _base_payload(self, user_id: str, /) -> BasePayload:
        return {
            "sub": user_id,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": self.utc_now(),
        }

    def create_access_token(self, user_id: str, /) -> str:
        base = self._base_payload(user_id)
        payload: AccessPayload = {
            **base,
            "type": "access",
            "exp": self.utc_now() + ACCESS_EXP,
        }
        return jwt.encode(dict(payload), JWT_SECRET, algorithm=JWT_ALGO)

    def create_refresh_token(self, user_id: str, jti: str, /) -> str:
        base = self._base_payload(user_id)
        payload: RefreshPayload = {
            **base,
            "type": "refresh",
            "jti": jti,
            "exp": self.utc_now() + REFRESH_EXP,
        }
        return jwt.encode(dict(payload), JWT_SECRET, algorithm=JWT_ALGO)

    async def create_or_get_refresh_token(self, user_id: str, /) -> str:
        pattern = "refresh:*"
        async for key in self.redis_client.scan_iter(pattern):
            if await self.redis_client.get(key) == user_id:
                token_identifier = key.split(":", 1)[1]
                return self.create_refresh_token(user_id, token_identifier)

        token_identifier = str(uuid.uuid4())
        await self.redis_client.setex(
            f"refresh:{token_identifier}",
            int(REFRESH_EXP.total_seconds()),
            user_id,
        )
        return self.create_refresh_token(user_id, token_identifier)

    async def login(self, user_id: str, /) -> TokenPairDict:
        return {
            "access_token": self.create_access_token(user_id),
            "refresh_token": await self.create_or_get_refresh_token(user_id),
            "expires_at_timestamp": int((self.utc_now() + ACCESS_EXP).timestamp()),
        }

    def _require_str(self, payload: Mapping[str, Any], key: str, /) -> str:
        value = payload.get(key)
        if isinstance(value, str):
            return value

        error_message = f"Invalid token payload: '{key!r}' must be a string"
        raise ValueError(error_message)

    def _require_int(self, payload: Mapping[str, Any], key: str, /) -> int:
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return int(value)

        error_message = f"Invalid token payload: '{key!r}' must be an integer"
        raise ValueError(error_message)

    def _require_literal(self, payload: Mapping[str, Any], key: str, expected: str, /) -> None:
        value = payload.get(key)
        if value == expected:
            return
        raise AuthError(f"Invalid token payload: '{key}' must be '{expected}'")

    @overload
    def decode(self, token: str, expected_type: Literal["access"], /) -> DecodedAccessPayload: ...

    @overload
    def decode(self, token: str, expected_type: Literal["refresh"], /) -> DecodedRefreshPayload: ...

    def decode(self, token: str, expected_type: Literal["access", "refresh"], /) -> DecodedAccessPayload | DecodedRefreshPayload:
        try:
            decoded = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGO],
                audience=AUDIENCE,
                issuer=ISSUER,
            )
        except jwt.ExpiredSignatureError:
            raise AuthError("Token expired")
        except jwt.InvalidTokenError:
            raise AuthError("Invalid token")

        if not isinstance(decoded, Mapping):
            raise AuthError("Invalid token payload")

        payload = decoded

        sub = self._require_str(payload, "sub")
        iss = self._require_str(payload, "iss")
        aud = self._require_str(payload, "aud")
        iat = self._require_int(payload, "iat")

        if expected_type == "access":
            self._require_literal(payload, "type", "access")
            exp = self._require_int(payload, "exp")
            return {
                "sub": sub,
                "iss": iss,
                "aud": aud,
                "iat": iat,
                "type": "access",
                "exp": exp,
            }

        self._require_literal(payload, "type", "refresh")
        jti = self._require_str(payload, "jti")
        exp = self._require_int(payload, "exp")
        return {
            "sub": sub,
            "iss": iss,
            "aud": aud,
            "iat": iat,
            "type": "refresh",
            "jti": jti,
            "exp": exp,
        }

    def authenticate(self, access_token: str) -> str:
        payload = self.decode(access_token, "access")
        return payload["sub"]

    async def refresh(self, refresh_token: str, /) -> TokenPairDict:
        payload = self.decode(refresh_token, "refresh")
        user_id = payload["sub"]
        jti = payload["jti"]
        key = f"refresh:{jti}"
        stored_user_id = await self.redis_client.get(key)
        if stored_user_id != user_id:
            raise AuthError("Invalid refresh token")

        return {
            "access_token": self.create_access_token(user_id),
            "refresh_token": await self.create_or_get_refresh_token(user_id),
            "expires_at_timestamp": int((self.utc_now() + ACCESS_EXP).timestamp()),
        }

    async def logout(self, refresh_token: str, /):
        payload = self.decode(refresh_token, "refresh")
        await self.redis_client.delete(f"refresh:{payload['jti']}")
