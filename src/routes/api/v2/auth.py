from __future__ import annotations

import uuid
from typing import Any

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
from src.models import AuthenticationProvider, CredentialsDict, UserDict
from src.utils import EmailNormalizer
from src.utils.token_manager import TokenManager, TokenPairDict

router: APIRouter = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
email_normalizer: EmailNormalizer = app.state.email_normalizer

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]


async def verify_google_id_token(id_token: str) -> dict[str, Any]:
    request_adapter = _aiohttp_requests.Request()

    try:
        id_info: dict[str, Any] = await _id_token_async.verify_oauth2_token(
            id_token,
            request_adapter,
        )
    except GoogleAuthError:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token.",
        )

    google_id: str | None = id_info.get("sub")
    if not google_id:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Invalid Google token.",
        )

    return id_info


async def login_if_google_id_exists(
    google_id: str,
) -> TokenPairDict | None:
    credentials = await credentials_collection.find_one({"google_id": google_id})

    if credentials is None:
        return None

    user_id: str = credentials["_id"]  # pyright: ignore
    return auth_manager.login(user_id)


async def link_google_to_existing_account(
    google_id: str,
    existing_email_address: str,
) -> str:
    now: float = arrow.utcnow().timestamp()
    normalized_email_result = await email_normalizer.normalize(existing_email_address)

    filter_query = {
        "$or": [
            {"email_address_normalized": normalized_email_result.cleaned_email},
            {"email_address": existing_email_address},
        ],
        "google_id": None,
    }

    update_query = {
        "$set": {
            "google_id": google_id,
            "last_login_timestamp": now,
        },
        "$addToSet": {
            "authentication_providers": AuthenticationProvider.GOOGLE,
        },
    }

    projection = {"_id": 1}

    result = await credentials_collection.find_one_and_update(
        filter_query,
        update_query,
        projection=projection,
    )

    if not result:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=("No matching account found for the provided existing email address or account is already linked to a Google ID."),
        )

    return result["_id"]  # pyright: ignore


async def create_new_google_account(google_id: str) -> str:
    now: float = arrow.utcnow().timestamp()

    credentials = CredentialsDict(
        _id=str(uuid.uuid4()),
        google_id=google_id,
        authentication_providers=[AuthenticationProvider.GOOGLE],
        created_at_timestamp=now,
        updated_at_timestamp=now,
        failed_login_attempts=0,
        failed_login_attempts_timestamp=0,
        last_login_timestamp=now,
    )

    await credentials_collection.insert_one(credentials)
    return credentials["_id"]  # pyright: ignore


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
    existing_email_address: str | None = Body(
        None,
        embed=True,
        description="The existing email address of the user, if linking accounts.",
        title="Existing Email Address",
        alias="existing_email_address",
    ),
) -> JSONResponse:
    id_info = await verify_google_id_token(id_token)
    google_id: str = id_info["sub"]

    token_pair = await login_if_google_id_exists(google_id)
    if token_pair is not None:
        return JSONResponse(content=token_pair, status_code=HTTP_200_OK)

    if existing_email_address:
        user_id = await link_google_to_existing_account(
            google_id,
            existing_email_address,
        )
    else:
        user_id = await create_new_google_account(google_id)

    token_pair = auth_manager.login(user_id)
    return JSONResponse(content=token_pair, status_code=HTTP_200_OK)
