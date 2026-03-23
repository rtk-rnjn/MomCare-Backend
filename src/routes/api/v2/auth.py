from __future__ import annotations

import uuid
from typing import Any, Literal, TypedDict

import arrow
import httpx
import jwt
import jwt.algorithms
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import load_dotenv
from fastapi import APIRouter, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import ORJSONResponse as JSONResponse
from pydantic import BaseModel
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis
from starlette.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED

from src.app import app
from src.models import (
    AccountStatus,
    AuthenticationProvider,
    CredentialsDict,
    ResponseCredentialsModel,
    UserDict,
)
from src.routes.api.utils import get_user_id
from src.utils import EmailNormalizer
from src.utils.token_manager import TokenManager, TokenPairDict

router: APIRouter = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
email_normalizer: EmailNormalizer = app.state.email_normalizer

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]

load_dotenv()

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_AUDIENCE = "com.Team05.MomCare"  # TODO: Update this to the actual Apple Service ID or Bundle ID used for Sign in with Apple
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"


class ErrorDetailModel(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ErrorResponseModel(BaseModel):
    detail: list[ErrorDetailModel] | str


class ApplePublicKey(TypedDict):
    kty: Literal["RSA"]
    kid: str
    use: Literal["sig"]
    alg: Literal["RS256"]
    n: str
    e: Literal["AQAB"]


class ApplePublicKeysResponse(TypedDict):
    keys: list[ApplePublicKey]


async def _fetch_apple_public_keys() -> ApplePublicKeysResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(APPLE_KEYS_URL)
        response.raise_for_status()
        return response.json()


async def fetch_apple_public_keys(redis_client: Redis) -> ApplePublicKeysResponse:
    cache_key = "apple_public_keys"
    cached_keys = await redis_client.get(cache_key)
    if cached_keys:
        return httpx.Response(200, content=cached_keys).json()

    keys = await _fetch_apple_public_keys()
    await redis_client.set(cache_key, httpx.Response(200, json=keys).content, ex=6 * 60 * 60)
    return keys


async def verify_apple_id_token(id_token: str, redis_client: Redis) -> dict[str, Any]:
    keys_response = await fetch_apple_public_keys(redis_client)
    keys = keys_response["keys"]

    unverified_header = jwt.get_unverified_header(id_token)
    kid = unverified_header.get("kid")

    key = next((k for k in keys if k["kid"] == kid), None)

    assert key is not None, "No matching Apple public key found for the provided ID token."
    key_dict = dict(key)

    algo: rsa.RSAPublicKey = jwt.algorithms.RSAAlgorithm.from_jwk(key_dict)  # pyright: ignore[reportAssignmentType]

    payload = jwt.decode(
        id_token,
        key=algo,
        algorithms=[key["alg"]],
        audience=APPLE_AUDIENCE,
        issuer=APPLE_ISSUER,
    )

    return payload


async def login_if_apple_id_exists(
    apple_id: str,
) -> TokenPairDict | None:
    credentials = await credentials_collection.find_one({"apple_id": apple_id})

    if credentials is None:
        return None

    user_id: str = credentials["_id"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
    return await auth_manager.login(user_id)


async def link_apple_to_existing_account(
    apple_id: str,
    existing_email_address: str,
) -> str:
    now: float = arrow.utcnow().timestamp()
    normalized_email_result = await email_normalizer.normalize(existing_email_address)

    filter_query = {
        "$or": [
            {"email_address_normalized": normalized_email_result.cleaned_email},
            {"email_address": existing_email_address},
        ],
        "apple_id": None,
    }

    update_query = {
        "$set": {
            "apple_id": apple_id,
            "last_login_timestamp": now,
        },
        "$addToSet": {
            "authentication_providers": AuthenticationProvider.APPLE,
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
            detail="No account found with that email address, or it is already linked to an Apple ID.",
        )

    return result["_id"]  # pyright: ignore[reportTypedDictNotRequiredAccess]


async def create_new_apple_account(apple_id: str) -> str:
    now: float = arrow.utcnow().timestamp()

    credentials = CredentialsDict(
        _id=str(uuid.uuid4()),
        apple_id=apple_id,
        authentication_providers=[AuthenticationProvider.APPLE],
        created_at_timestamp=now,
        updated_at_timestamp=now,
        failed_login_attempts=0,
        failed_login_attempts_timestamp=0,
        last_login_timestamp=now,
        account_status=AccountStatus.ACTIVE,
    )

    await credentials_collection.insert_one(credentials)
    await users_collection.insert_one({"_id": credentials["_id"]})  # pyright: ignore[reportTypedDictNotRequiredAccess]
    return credentials["_id"]  # pyright: ignore


@router.post(
    "/ios/apple-login",
    name="Apple Login",
    status_code=HTTP_200_OK,
    response_model=TokenPairDict,
    description="Authenticate a user using an Apple ID token and return access and refresh tokens.",
    response_description="A pair of access and refresh tokens for the authenticated user.",
    responses={
        HTTP_400_BAD_REQUEST: {
            "description": "Invalid Apple ID token payload.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_401_UNAUTHORIZED: {
            "description": "Token verification failed.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def apple_login(
    id_token: str = Body(
        ...,
        embed=True,
        description="The ID token obtained from Apple Sign-In.",
        title="Apple Login",
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
    try:
        id_info = await verify_apple_id_token(id_token, redis_client)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Apple ID token is invalid or has expired. Please sign in with Apple again.",
        )

    apple_id: str = id_info["sub"]

    token_pair = await login_if_apple_id_exists(apple_id)
    if token_pair is not None:
        return JSONResponse(content=token_pair, status_code=HTTP_200_OK)
    if existing_email_address:
        user_id = await link_apple_to_existing_account(
            apple_id,
            existing_email_address,
        )
    else:
        user_id = await create_new_apple_account(apple_id)

    token_pair = await auth_manager.login(user_id)
    return JSONResponse(content=token_pair, status_code=HTTP_200_OK)


@router.get(
    "/credentials",
    name="Get User Credentials",
    status_code=HTTP_200_OK,
    response_model=ResponseCredentialsModel,
    description="Retrieve the authentication credentials and account status for the currently authenticated user.",
    response_description="The user's authentication credentials and account status.",
    responses={
        HTTP_401_UNAUTHORIZED: {
            "description": "Unauthorized access due to missing or invalid token.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def get_user_credentials(
    user_id: str = Depends(get_user_id),
) -> JSONResponse:
    credentials = await credentials_collection.find_one({"_id": user_id})
    if credentials is None:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="No credentials found for this account. Please log in again.")

    response_model = ResponseCredentialsModel(
        email_address=credentials.get("email_address"),
        apple_id=credentials.get("apple_id"),
        authentication_providers=credentials.get("authentication_providers", []),
        account_status=AccountStatus.from_str(credentials.get("account_status", "active")),
        verified_email=credentials.get("verified_email", False),
    )
    return JSONResponse(response_model.model_dump(by_alias=True), status_code=HTTP_200_OK)
