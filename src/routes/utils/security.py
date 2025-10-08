from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.app import token_handler

security = HTTPBearer()


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = token_handler.decode_token(credentials.credentials)

    if token is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token
