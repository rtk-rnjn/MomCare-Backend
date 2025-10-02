from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final, TypedDict, cast

from jwt import decode, encode
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from pydantic import BaseModel, Field
from pytz import timezone

if TYPE_CHECKING:
    from src.models import User


class Token(BaseModel):
    sub: str
    email: str
    verified: bool
    name: str
    iat: int = Field(default_factory=lambda: int(datetime.now(timezone("UTC")).timestamp()))
    exp: int


class TokenDict(TypedDict):
    sub: str
    email: str
    verified: bool
    name: str
    iat: int
    exp: int


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret: Final[str] = secret
        self.algorithm: Final[str] = algorithm

    def create_access_token(self, user: User, expire_in: int = 360) -> str:
        payload = Token(
            sub=user.id,
            email=user.email_address,
            verified=user.is_verified,
            name="%s %s" % (user.first_name, user.last_name),
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
