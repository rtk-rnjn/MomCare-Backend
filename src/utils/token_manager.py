from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, TypedDict, overload

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

JWT_LEEWAY_SECONDS = int(os.getenv("JWT_LEEWAY_SECONDS", "30"))

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
    expires_at_timestamp: int


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class RedisKeys:
    refresh_prefix: str = "refresh"
    user_refresh_set_prefix: str = "user_refresh_set"

    def refresh_jti(self, jti: str) -> str:
        return f"{self.refresh_prefix}:{jti}"

    def user_refresh_set(self, user_id: str) -> str:
        return f"{self.user_refresh_set_prefix}:{user_id}"


_KEYS = RedisKeys()


class TokenManager:
    def __init__(self):
        self.redis_client = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )

    # ---- time helpers ----
    def utc_now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _base_payload(self, user_id: str, /) -> BasePayload:
        return {
            "sub": user_id,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": self.utc_now(),
        }

    # ---- token creation ----
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

    async def _store_refresh_session(self, user_id: str, jti: str, /) -> None:
        ttl = int(REFRESH_EXP.total_seconds())
        refresh_key = _KEYS.refresh_jti(jti)
        set_key = _KEYS.user_refresh_set(user_id)

        async with self.redis_client.pipeline(transaction=True) as pipe:
            pipe.setex(refresh_key, ttl, user_id)
            pipe.sadd(set_key, jti)
            pipe.expire(set_key, ttl)
            await pipe.execute()

    async def _revoke_refresh_session(self, user_id: str, jti: str, /) -> None:
        refresh_key = _KEYS.refresh_jti(jti)
        set_key = _KEYS.user_refresh_set(user_id)

        async with self.redis_client.pipeline(transaction=True) as pipe:
            pipe.delete(refresh_key)
            pipe.srem(set_key, jti)
            await pipe.execute()

    def _require_str(self, payload: Mapping[str, Any], key: str, /) -> str:
        value = payload.get(key)
        if isinstance(value, str):
            return value
        raise AuthError(f"Invalid token payload: '{key}' must be a string")

    def _require_int(self, payload: Mapping[str, Any], key: str, /) -> int:
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return int(value)
        raise AuthError(f"Invalid token payload: '{key}' must be an integer")

    def _require_literal(self, payload: Mapping[str, Any], key: str, expected: str, /) -> None:
        if payload.get(key) != expected:
            raise AuthError(f"Invalid token payload: '{key}' must be '{expected}'")

    @overload
    def decode(self, token: str, expected_type: Literal["access"], /) -> DecodedAccessPayload: ...
    @overload
    def decode(self, token: str, expected_type: Literal["refresh"], /) -> DecodedRefreshPayload: ...

    def decode(
        self,
        token: str,
        expected_type: Literal["access", "refresh"],
        /,
    ) -> DecodedAccessPayload | DecodedRefreshPayload:
        try:
            decoded = jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGO],
                audience=AUDIENCE,
                issuer=ISSUER,
                leeway=JWT_LEEWAY_SECONDS,
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                },
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

    async def login(self, user_id: str, /) -> TokenPairDict:
        jti = str(uuid.uuid4())
        await self._store_refresh_session(user_id, jti)

        return {
            "access_token": self.create_access_token(user_id),
            "refresh_token": self.create_refresh_token(user_id, jti),
            "expires_at_timestamp": int((self.utc_now() + ACCESS_EXP).timestamp()),
        }

    def authenticate(self, access_token: str) -> str:
        payload = self.decode(access_token, "access")
        return payload["sub"]

    async def refresh(self, refresh_token: str, /) -> TokenPairDict:
        payload = self.decode(refresh_token, "refresh")
        user_id = payload["sub"]
        old_jti = payload["jti"]

        old_key = _KEYS.refresh_jti(old_jti)
        stored_user_id = await self.redis_client.get(old_key)

        if stored_user_id is None:
            raise AuthError("Refresh token revoked or expired (server-side session not found)")

        if stored_user_id != user_id:
            raise AuthError("Invalid refresh token (session mismatch)")

        new_jti = str(uuid.uuid4())
        ttl = int(REFRESH_EXP.total_seconds())
        new_key = _KEYS.refresh_jti(new_jti)
        set_key = _KEYS.user_refresh_set(user_id)

        async with self.redis_client.pipeline(transaction=True) as pipe:
            pipe.delete(old_key)
            pipe.srem(set_key, old_jti)

            pipe.setex(new_key, ttl, user_id)
            pipe.sadd(set_key, new_jti)
            pipe.expire(set_key, ttl)
            await pipe.execute()

        return {
            "access_token": self.create_access_token(user_id),
            "refresh_token": self.create_refresh_token(user_id, new_jti),
            "expires_at_timestamp": int((self.utc_now() + ACCESS_EXP).timestamp()),
        }

    async def logout(self, refresh_token: str, /) -> None:
        payload = self.decode(refresh_token, "refresh")
        await self._revoke_refresh_session(payload["sub"], payload["jti"])

    async def logout_everywhere(self, user_id: str, /) -> None:
        set_key = _KEYS.user_refresh_set(user_id)
        jtis = self.redis_client.smembers(set_key)
        if not isinstance(jtis, set):
            jtis = await jtis

        if not jtis:
            return

        async with self.redis_client.pipeline(transaction=True) as pipe:
            for jti in jtis:
                pipe.delete(_KEYS.refresh_jti(jti))
            pipe.delete(set_key)
            await pipe.execute()
