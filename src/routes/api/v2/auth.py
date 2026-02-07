from __future__ import annotations

import uuid

import arrow
from fastapi import APIRouter, Body
from fastapi.exceptions import HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import _aiohttp_requests
from google.oauth2 import _id_token_async
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis

from src.app import app
from src.models import CredentialsDict, UserDict
from src.utils.token_manager import TokenManager, TokenPair

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]


@router.post("/google-login", response_model=TokenPair)
async def google_login(token: str = Body(..., embed=True)):
    google_request_adapter = _aiohttp_requests.Request()
    try:
        id_info = await _id_token_async.verify_oauth2_token(token, google_request_adapter)
    except GoogleAuthError:
        raise HTTPException(status_code=401, detail="Invalid Google token.")

    if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
        raise HTTPException(status_code=401, detail="Invalid Google token issuer.")

    google_id = id_info.get("sub")
    email = id_info.get("email")

    if not google_id or not email:
        raise HTTPException(status_code=400, detail="Google token missing required fields.")

    cred = await credentials_collection.find_one({"google_id": google_id})
    now = arrow.utcnow().timestamp()

    if cred is None:
        cred_id = str(uuid.uuid4())
        credential_dict = CredentialsDict(
            _id=cred_id,
            email_address=email,
            password=None,
            google_id=google_id,
            apple_id=None,
            created_at_timestamp=now,
            last_login_timestamp=now,
            verified_email=True,
        )

        await credentials_collection.insert_one(credential_dict)
        await users_collection.insert_one({"_id": cred_id})
    else:
        cred_id = str(cred.get("_id"))
        await credentials_collection.update_one(
            {"_id": cred_id},
            {"$set": {"last_login_timestamp": now}},
        )

    return auth_manager.login(cred_id)
