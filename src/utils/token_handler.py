from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

import jwt
from pydantic import BaseModel
from pytz import timezone

from src.models import User

if TYPE_CHECKING:
    pass


class Token(BaseModel):
    sub: str
    email: str
    name: str
    iat: int = int(datetime.now(timezone("UTC")).timestamp())
    exp: int


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm

    def create_access_token(self, user: User, expire_in: int = 360) -> str:
        payload = Token(
            sub=user.id,
            email=user.email_address,
            name=f"{user.first_name} {user.last_name}",
            exp=int((datetime.now(timezone("UTC")) + timedelta(seconds=expire_in)).timestamp()),
        )

        return jwt.encode(dict(payload), self.secret, algorithm=self.algorithm)

    def validate_token(self, token: str) -> Optional[Token]:
        try:
            return Token(**jwt.decode(token, self.secret, algorithms=[self.algorithm]))
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def decode_token(self, token: str) -> Optional[Token]:
        try:
            return Token(
                **jwt.decode(
                    token,
                    self.secret,
                    algorithms=[self.algorithm],
                )
            )
        except jwt.InvalidTokenError:
            raise
