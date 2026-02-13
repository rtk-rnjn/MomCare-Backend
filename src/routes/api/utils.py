from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.app import app
from src.utils import AuthError, TokenManager

security = HTTPBearer()
auth_manager: TokenManager = app.state.auth_manager


def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return auth_manager.authenticate(credentials.credentials)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


def get_access_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return auth_manager.decode(credentials.credentials, "access")
    except AuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


def get_refresh_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return auth_manager.decode(credentials.credentials, "refresh")
    except AuthError as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")
