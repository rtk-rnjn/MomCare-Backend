from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final, TypedDict, cast

from jwt import decode, encode
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, Field
from pytz import timezone

from src.models.user import UserDict as User


class Token(BaseModel):
    sub: str
    email: str
    verified: bool
    iat: int = Field(default_factory=lambda: int(datetime.now(timezone("UTC")).timestamp()))
    exp: int


class TokenDict(TypedDict):
    sub: str
    email: str
    verified: bool
    iat: int
    exp: int


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret: Final[str] = secret
        self.algorithm: Final[str] = algorithm

    def create_access_token(self, user: User, expire_in: int = 60 * 60 * 24) -> str:
        payload = Token(
            sub=user["id"],  # type: ignore
            email=user["email_address"],  # type: ignore
            verified=user["is_verified"],  # type: ignore
            exp=int((datetime.now(timezone("UTC")) + timedelta(seconds=expire_in)).timestamp()),
        )
        token = encode(dict(payload), self.secret, algorithm=self.algorithm)
        return token

    def validate_token(self, token: str) -> Token | None:
        try:
            decoded = cast(TokenDict, decode(token, self.secret, algorithms=[self.algorithm]))
            return Token(**decoded)

        except ExpiredSignatureError:
            return None
        except InvalidTokenError:
            return None

    def decode_token(self, token: str) -> Token | None:
        return self.validate_token(token)
