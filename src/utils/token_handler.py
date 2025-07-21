from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

import jwt
from pydantic import BaseModel, Field
from pytz import timezone

from src.models import User
from src.utils.log import log

if TYPE_CHECKING:
    pass


class Token(BaseModel):
    sub: str
    email: str
    verified: bool
    name: str
    iat: int = Field(default_factory=lambda: int(datetime.now(timezone("UTC")).timestamp()))
    exp: int


class TokenHandler:
    def __init__(self, secret: str, algorithm: str = "HS256"):
        self.secret = secret
        self.algorithm = algorithm

    def create_access_token(self, user: User, expire_in: int = 360) -> str:
        log.debug("Creating access token for user: %s", user.id)
        payload = Token(
            sub=user.id,
            email=user.email_address,
            verified=user.is_verified,
            name="%s %s" % (user.first_name, user.last_name),
            exp=int((datetime.now(timezone("UTC")) + timedelta(seconds=expire_in)).timestamp()),
        )
        token = jwt.encode(dict(payload), self.secret, algorithm=self.algorithm)
        log.info("Access token created for user: %s", user.id)
        return token

    def validate_token(self, token: str) -> Optional[Token]:
        log.debug("Validating token")
        try:
            decoded = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            log.info("Token successfully validated")
            obj = Token(**decoded)
            if not obj.verified:
                log.warning("Token is not verified")
                return None
            return obj

        except jwt.ExpiredSignatureError:
            log.warning("Token has expired")
            return None
        except jwt.InvalidTokenError:
            log.error("Invalid token provided")
            return None

    def decode_token(self, token: str) -> Optional[Token]:
        return self.validate_token(token)
