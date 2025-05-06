from __future__ import annotations
from typing import Optional

from src.app import app, genai_handler, cache_handler
from fastapi import APIRouter, Request
import os
from fastapi import Depends, HTTPException
from src.models.myplan import MyPlan
from src.utils import Token, TokenHandler
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.models import User

security = HTTPBearer()

token_handler = TokenHandler(os.environ["JWT_SECRET"])
security = HTTPBearer()


def get_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return token_handler.decode_token(credentials.credentials)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e
    

router = APIRouter(prefix="/plan", tags=["Plan"])

@router.get("/")
async def get_plan(request: Request, token: Token = Depends(get_user_token)) -> Optional[MyPlan]:
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return await genai_handler.generate_plan(user)

app.include_router(router)
