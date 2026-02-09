from __future__ import annotations

import uuid

import arrow
from fastapi import APIRouter, Body
from fastapi.exceptions import HTTPException
from fastapi.responses import ORJSONResponse as JSONResponse
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import _aiohttp_requests
from google.oauth2 import _id_token_async
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis
from starlette.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED

from src.app import app
from src.models import CredentialsDict, UserDict
from src.utils.token_manager import TokenManager, TokenPairDict

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]


@router.post(
    "/ios/google-login",
    name="Google Login",
    status_code=HTTP_200_OK,
    response_model=TokenPairDict,
    description="Authenticate a user using a Google ID token and return access and refresh tokens.",
    response_description="A pair of access and refresh tokens for the authenticated user.",
    responses={
        HTTP_200_OK: {"description": "User authenticated successfully."},
        HTTP_400_BAD_REQUEST: {"description": "Invalid Google token."},
        HTTP_401_UNAUTHORIZED: {"description": "Unauthorized. Invalid or missing Google token."},
    },
)
async def google_login(
    id_token: str = Body(
        ...,
        embed=True,
        description="The ID token obtained from Google Sign-In.",
        title="Google Login",
        alias="id_token",
    ),
) -> JSONResponse:
    google_request_adapter = _aiohttp_requests.Request()
    try:
        id_info = await _id_token_async.verify_oauth2_token(id_token, google_request_adapter)
    except GoogleAuthError:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid Google token.")

    google_id = id_info.get("sub")
    email = id_info.get("email")

    if not google_id or not email:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Google token missing required fields.")

    cred = await credentials_collection.find_one({"google_id": google_id})
    now = arrow.utcnow().timestamp()

    if cred is None:
        cred_id = str(uuid.uuid4())
        credential_dict = CredentialsDict()

        await credentials_collection.insert_one(credential_dict)
        await users_collection.insert_one({"_id": cred_id})
    else:
        cred_id = str(cred.get("_id"))
        await credentials_collection.update_one(
            {"_id": cred_id},
            {"$set": {"last_login_timestamp": now}},
        )

    return JSONResponse(auth_manager.login(cred_id))
