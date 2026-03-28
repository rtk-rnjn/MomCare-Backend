from __future__ import annotations

import inspect
import uuid

import arrow
import bcrypt
from fastapi import APIRouter, BackgroundTasks, Body, Depends
from fastapi.exceptions import HTTPException
from fastapi.responses import ORJSONResponse as JSONResponse
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_410_GONE,
    HTTP_423_LOCKED,
)

from src.app import app
from src.models import (
    AccountStatus,
    AuthenticationProvider,
    CredentialsDict,
    CredentialsModel,
    PasswordAlgorithm,
    UserDict,
    UserModel,
)
from src.routes.api.utils import get_user_id
from src.utils import RNG, EmailHandler, EmailNormalizer
from src.utils.token_manager import AuthError, TokenManager, TokenPairDict

from .objects import ErrorResponseModel, RegistrationResponse, ServerMessage

router = APIRouter(prefix="/auth", tags=["Authentication"])

auth_manager: TokenManager = app.state.auth_manager
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
email_normalizer: EmailNormalizer = app.state.email_normalizer
rng: RNG = app.state.rng

credentials_collection: Collection[CredentialsDict] = database["credentials"]
users_collection: Collection[UserDict] = database["users"]

email_handler = EmailHandler()


def _hash_password(password: str, /, *, algorithm: PasswordAlgorithm = PasswordAlgorithm.BCRYPT) -> str:
    if algorithm == PasswordAlgorithm.BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    raise ValueError("Unsupported password algorithm")


def _verify_password(*, password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


async def _get_credential_by_email(email_address: str, /) -> CredentialsDict:
    normalization_result = await email_normalizer.normalize(email_address)
    cred = await credentials_collection.find_one(
        {
            "$or": [
                {"email_address": email_address},
                {"email_address_normalized": normalization_result.cleaned_email},
            ],
            "password_hash": {"$exists": True},
            "account_status": {"$ne": AccountStatus.DELETED},
        }
    )
    if cred is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No account found with that email address.")
    return cred


async def _get_credential_by_id(user_id: str, /) -> CredentialsDict:
    cred = await credentials_collection.find_one({"_id": user_id})
    if cred is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found.")

    if cred.get("account_status") == AccountStatus.DELETED:
        raise HTTPException(status_code=HTTP_410_GONE, detail="This account has been deleted.")

    if cred.get("account_status") == AccountStatus.LOCKED:
        raise HTTPException(status_code=HTTP_423_LOCKED, detail="Your account is locked. Please contact support.")
    return cred


def _create_json_response(*, detail: str, status: int = HTTP_200_OK):
    return JSONResponse(content={"detail": detail}, status_code=status)


@router.post(
    "/register",
    name="Register User",
    status_code=HTTP_201_CREATED,
    response_model=RegistrationResponse,
    response_description="The registered email address along with access and refresh tokens for authentication.",
    summary="Register a new user account",
    description="Create a new user account using an email address and password. Returns the registered email address along with access and refresh tokens for authentication.",
    responses={
        HTTP_400_BAD_REQUEST: {
            "description": "Missing email or password.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_409_CONFLICT: {
            "description": "Email already registered.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def register(data: CredentialsModel = Body(...)):
    if not data.email_address or not data.password:
        raise HTTPException(status_code=400, detail="Email address and password are required.")

    normalization_result = await email_normalizer.normalize(data.email_address)
    if await credentials_collection.find_one(
        {
            "$or": [
                {"email_address": data.email_address},
                {"email_address_normalized": normalization_result.cleaned_email},
            ],
            "account_status": {"$ne": AccountStatus.DELETED},
        }
    ):
        raise HTTPException(status_code=409, detail="An account with this email address already exists.")

    cred_id = str(uuid.uuid4())

    now = arrow.utcnow().timestamp()

    credential = CredentialsDict(
        _id=cred_id,
        email_address=data.email_address,
        email_address_normalized=normalization_result.cleaned_email,
        email_address_provider=normalization_result.mailbox_provider,
        password_hash=_hash_password(data.password),
        password_algo=PasswordAlgorithm.BCRYPT,
        created_at_timestamp=now,
        updated_at_timestamp=now,
        authentication_providers=[AuthenticationProvider.INTERNAL],
        account_status=AccountStatus.ACTIVE,
        verified_email=False,
    )
    await credentials_collection.insert_one(credential)

    await users_collection.insert_one({"_id": cred_id})

    tokens = await auth_manager.login(cred_id)
    return RegistrationResponse(email_address=data.email_address, **tokens)


@router.post(
    "/login",
    name="Login User",
    status_code=HTTP_200_OK,
    response_model=TokenPairDict,
    summary="Login to user account",
    description="Authenticate a user using their email address and password. Returns access and refresh tokens for authentication if the credentials are valid.",
    responses={
        HTTP_400_BAD_REQUEST: {
            "description": "Missing email or password.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_401_UNAUTHORIZED: {
            "description": "Invalid credentials or account status prevents login.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {
            "description": "Account deleted.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_423_LOCKED: {
            "description": "Account locked.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def login(data: CredentialsModel = Body(...)):
    if not data.email_address or not data.password:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Email address and password are required.")

    cred = await _get_credential_by_email(data.email_address)

    now = arrow.utcnow().timestamp()

    if not _verify_password(password=data.password, hashed=cred.get("password_hash") or _hash_password("")):
        await credentials_collection.update_one(
            {"_id": cred.get("_id")},
            {
                "$inc": {"failed_login_attempts": 1},
                "$set": {"failed_login_attempts_timestamp": now},
            },
        )
        raise HTTPException(status_code=401, detail="Incorrect password. Please try again.")

    await credentials_collection.update_one(
        {"_id": cred.get("_id")},
        {
            "$set": {
                "last_login_timestamp": now,
                "failed_login_attempts": 0,
                "failed_login_attempts_timestamp": None,
            },
        },
    )

    redis_key = f"token:{cred.get('_id')}"

    token_pair_dict = redis_client.hgetall(redis_key)
    if inspect.isawaitable(token_pair_dict):
        token_pair_dict = await token_pair_dict

    if token_pair_dict and float(token_pair_dict["expires_at_timestamp"]) > arrow.utcnow().timestamp():
        return JSONResponse(
            TokenPairDict(
                access_token=token_pair_dict["access_token"],
                refresh_token=token_pair_dict["refresh_token"],
                expires_at_timestamp=float(token_pair_dict["expires_at_timestamp"]),
            ),
            status_code=HTTP_200_OK,
        )

    token_pair = await auth_manager.login(str(cred.get("_id")))
    maybe_awaitable = redis_client.hset(redis_key, mapping=dict(token_pair))
    await redis_client.expire(redis_key, 15 * 60)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable

    return JSONResponse(token_pair, status_code=HTTP_200_OK)


@router.get(
    "/me",
    name="Get Current User",
    status_code=HTTP_200_OK,
    response_model=UserModel,
    summary="Get current authenticated user",
    description="Retrieve the details of the currently authenticated user. Requires a valid access token.",
    responses={
        HTTP_404_NOT_FOUND: {
            "description": "User not found for provided token.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        }
    },
)
async def get_current_user(user_id: str = Depends(get_user_id, use_cache=False)):
    user = await users_collection.find_one({"_id": user_id})
    if user is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found.")
    return UserModel.model_validate(user)


@router.post(
    "/refresh",
    name="Refresh Token",
    status_code=HTTP_200_OK,
    response_model=TokenPairDict,
    summary="Refresh authentication tokens",
    description="Obtain new access and refresh tokens using a valid refresh token. Returns new tokens if the provided refresh token is valid.",
    responses={
        HTTP_401_UNAUTHORIZED: {
            "description": "Invalid refresh token.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        }
    },
)
async def refresh_token(
    refresh_token: str = Body(
        embed=True,
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        description="The refresh token used to obtain new authentication tokens.",
        title="Refresh Token",
        alias="refresh_token",
    ),
):
    try:
        return await auth_manager.refresh(refresh_token)
    except AuthError as e:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=f"Refresh token error: {str(e)}. Please log in again.") from e


@router.post(
    "/logout",
    name="Logout User",
    status_code=HTTP_200_OK,
    response_model=ServerMessage,
    summary="Logout user",
    description="Invalidate the provided refresh token to log the user out. Requires a valid refresh token. Returns a message confirming successful logout if the token is valid.",
    responses={
        HTTP_401_UNAUTHORIZED: {
            "description": "Invalid refresh token.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        }
    },
)
async def logout(
    refresh_token: str = Body(
        embed=True,
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
        description="The refresh token to invalidate for logging out.",
        title="Refresh Token",
        alias="refresh_token",
    ),
):
    try:
        await auth_manager.logout(refresh_token)
    except AuthError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token. Please log in again.")
    return _create_json_response(detail="Logged out successfully.")


@router.patch(
    "/update",
    name="Update User Details",
    status_code=HTTP_200_OK,
    response_model=ServerMessage,
    summary="Update current user details",
    description="Update the details of the currently authenticated user. Requires a valid access token. Accepts any subset of user fields to update and returns a message confirming successful update.",
    responses={
        HTTP_400_BAD_REQUEST: {
            "description": "No updatable fields provided.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_401_UNAUTHORIZED: {
            "description": "Account deleted; unauthorized to update.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_423_LOCKED: {
            "description": "Account locked.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def update_user(
    updated_data: UserModel = Body(...),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    fields = updated_data.model_dump(exclude_unset=True, by_alias=True)
    fields.pop("id", None)
    fields.pop("_id", None)

    if not fields:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No updatable fields were provided.")

    credential = await credentials_collection.find_one_and_update(
        {"_id": user_id},
        {"$set": {"updated_at_timestamp": arrow.utcnow().timestamp()}},
        return_document=ReturnDocument.AFTER,
    )

    if credential is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found.")

    if credential.get("account_status") == AccountStatus.DELETED:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="This account has been deleted and cannot be updated.")

    if credential.get("account_status") == AccountStatus.LOCKED:
        raise HTTPException(status_code=HTTP_423_LOCKED, detail="Your account is locked. Please contact support.")

    update_result = await users_collection.update_one({"_id": user_id}, {"$set": fields})
    if update_result.matched_count == 0:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User profile not found.")

    return _create_json_response(detail="User updated successfully.")


@router.delete(
    "/delete",
    name="Delete User Account",
    status_code=HTTP_200_OK,
    response_model=bool,
    response_description="A message confirming successful deletion of the user account.",
    summary="Delete current user account",
    description="Permanently delete the currently authenticated user's account. Requires a valid access token. Deletes the user's credentials and details from the database and returns a message confirming successful deletion.",
    responses={
        HTTP_404_NOT_FOUND: {
            "description": "User not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def delete_user(user_id: str = Depends(get_user_id, use_cache=False)):
    update_result = await credentials_collection.update_one(
        {"_id": user_id},
        {"$set": {"account_status": AccountStatus.DELETED, "updated_at_timestamp": arrow.utcnow().timestamp()}},
    )
    if update_result.matched_count == 0:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found.")

    await users_collection.delete_one({"_id": user_id})
    return True


@router.patch(
    "/change-email",
    name="Change User Email",
    status_code=HTTP_200_OK,
    response_model=ServerMessage,
    response_description="A message confirming successful email change.",
    summary="Change user email address",
    description="Change the email address of the currently authenticated user. Requires a valid access token. Accepts the new email address, updates it in the user's credentials, and returns a message confirming successful email change.",
    responses={
        HTTP_404_NOT_FOUND: {
            "description": "User not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_409_CONFLICT: {
            "description": "Email already in use.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def change_email(
    new_email_address: str = Body(
        embed=True,
        examples=["new_email@example.com"],
        description="The user's new email address.",
        title="New Email Address",
        alias="new_email_address",
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    cred = await _get_credential_by_id(user_id)
    if not cred:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found.")

    normalised_email_result = await email_normalizer.normalize(new_email_address)

    existing_user = await credentials_collection.find_one(
        {
            "$or": [
                {"email_address": new_email_address},
                {"email_address_normalized": normalised_email_result.cleaned_email},
            ]
        }
    )
    if existing_user and existing_user.get("_id") != user_id and existing_user.get("account_status") != AccountStatus.DELETED:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail="That email address is already in use by another account.")

    await credentials_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "email_address": new_email_address,
                "email_address_normalized": normalised_email_result.cleaned_email,
                "email_address_provider": normalised_email_result.mailbox_provider,
                "verified_email": False,
                "updated_at_timestamp": arrow.utcnow().timestamp(),
            },
        },
    )

    refresh_token = await auth_manager.create_or_get_refresh_token(user_id)
    await auth_manager.logout(refresh_token)

    return _create_json_response(detail="Email address changed successfully.")


@router.patch(
    "/change-password",
    response_model=ServerMessage,
    response_description="A message confirming successful password change.",
    name="Change User Password",
    status_code=HTTP_200_OK,
    summary="Change user password",
    description="Change the password of the currently authenticated user. Requires a valid access token. Accepts the current password and the new password, verifies the current password, and updates to the new password if valid. Returns a message confirming successful password change.",
    responses={
        HTTP_401_UNAUTHORIZED: {
            "description": "Current password incorrect.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "User not found.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_423_LOCKED: {
            "description": "Account locked.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_410_GONE: {
            "description": "Account deleted.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def change_password(
    current_password: str = Body(
        embed=True,
        examples=["current_password123"],
        description="The user's current password.",
        title="Current Password",
        alias="current_password",
    ),
    new_password: str = Body(
        embed=True, examples=["new_password123"], description="The user's new password.", title="New Password", alias="new_password"
    ),
    user_id: str = Depends(get_user_id, use_cache=False),
):
    cred = await _get_credential_by_id(user_id)

    if not _verify_password(password=current_password, hashed=cred.get("password_hash") or _hash_password("")):
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Current password is incorrect.")

    await credentials_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "password_hash": _hash_password(new_password),
                "password_algo": PasswordAlgorithm.BCRYPT,
                "updated_at_timestamp": arrow.utcnow().timestamp(),
            },
        },
    )

    refresh_token = await auth_manager.create_or_get_refresh_token(user_id)
    await auth_manager.logout(refresh_token)

    return _create_json_response(detail="Password changed successfully.")


@router.post(
    "/request-otp",
    name="Request OTP for Email Verification",
    status_code=HTTP_200_OK,
    response_model=ServerMessage,
    response_description="A message confirming that the OTP was sent successfully.",
    summary="Request OTP for email verification",
    description="Request a One-Time Password (OTP) to be sent to the user's email address for verification purposes. Accepts the user's email address and sends an OTP to that address if it exists in the system. Returns a message confirming that the OTP was sent successfully.",
    responses={
        HTTP_404_NOT_FOUND: {
            "description": "Email not registered.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def request_otp(
    background_tasks: BackgroundTasks,
    email_address: str = Body(
        embed=True,
        examples=["user@example.com"],
        description="The email address to which the OTP should be sent.",
        title="Email Address",
        alias="email_address",
    ),
):
    await _get_credential_by_email(email_address)
    otp = str(rng.random_int(start=100000, end=999999))
    await redis_client.setex(f"otp:{email_address}", 600, otp)

    background_tasks.add_task(
        email_handler.send_verification_email,
        to=email_address,
        subject="Your MomCare OTP",
        otp=otp,
    )

    return _create_json_response(detail="OTP sent successfully.")


@router.post(
    "/verify-otp",
    response_model=ServerMessage,
    response_description="A message confirming successful OTP verification.",
    name="Verify OTP for Email Verification",
    status_code=HTTP_200_OK,
    summary="Verify OTP for email verification",
    description="Verify a One-Time Password (OTP) sent to the user's email address for verification purposes. Accepts the user's email address and the OTP, and verifies the OTP if it matches the one stored in the system. Returns a message confirming successful verification.",
    responses={
        HTTP_400_BAD_REQUEST: {
            "description": "OTP invalid or expired.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "Email not registered.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def verify_otp(
    email_address: str = Body(
        embed=True,
        examples=["user@example.com"],
        description="The email address associated with the OTP.",
        title="Email Address",
        alias="email_address",
    ),
    otp: str = Body(
        embed=True,
        examples=["123456"],
        description="The OTP to verify.",
        title="OTP",
        alias="otp",
    ),
):
    cred = await _get_credential_by_email(email_address)
    stored = redis_client.get(f"otp:{email_address}")
    if inspect.isawaitable(stored):
        stored = await stored

    if stored is None or stored != otp:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="The OTP is invalid or has expired. Please request a new one.",
        )

    await credentials_collection.update_one(
        {"_id": cred.get("_id")},
        {
            "$set": {
                "verified_email": True,
                "verified_email_at_timestamp": arrow.utcnow().timestamp(),
            },
        },
    )

    return _create_json_response(detail="OTP verified successfully.")


@router.post(
    "/forget-password",
    name="Forget Password",
    status_code=HTTP_200_OK,
    description="Initiate the password reset process for a user who has forgotten their password.",
    responses={
        HTTP_200_OK: {
            "description": "Password reset initiated successfully. An email with reset instructions has been sent if the email address exists in our system.",
        },
        HTTP_404_NOT_FOUND: {
            "description": "No account found with the provided email address.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def forget_password(
    background_tasks: BackgroundTasks,
    email_address: str = Body(
        ...,
        embed=True,
        description="The email address associated with the user's account.",
        title="Email Address",
        alias="email_address",
    ),
) -> JSONResponse:
    normalized_email_result = await email_normalizer.normalize(email_address)
    normalized_email_address = normalized_email_result.cleaned_email

    credentials = await credentials_collection.find_one(
        {
            "$or": [
                {"email_address_normalized": normalized_email_address},
                {"email_address": email_address},
            ],
            "account_status": AccountStatus.ACTIVE.value,
        }
    )
    if credentials is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No account found with that email address.")

    user_id = credentials["_id"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
    otp = str(rng.random_int(start=100000, end=999999))
    await redis_client.setex(f"forget_password_otp:{user_id}", 600, otp)

    background_tasks.add_task(
        email_handler.send_forget_password_email,
        to=email_address,
        subject="Your MomCare Password Reset OTP",
        otp=otp,
    )

    return _create_json_response(detail="If an account with that email address exists, a password reset OTP has been sent.")


@router.post(
    "/reset-password",
    name="Reset Password",
    status_code=HTTP_200_OK,
    description="Reset the user's password using a valid OTP sent to their email address.",
    responses={
        HTTP_200_OK: {
            "description": "Password reset successfully.",
        },
        HTTP_400_BAD_REQUEST: {
            "description": "Invalid or expired OTP.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
        HTTP_404_NOT_FOUND: {
            "description": "No account found for the provided email address.",
            "model": ErrorResponseModel,
            "content": {"application/json": {}},
        },
    },
)
async def reset_password(
    email_address: str = Body(
        ...,
        embed=True,
        description="The email address associated with the user's account.",
        title="Email Address",
        alias="email_address",
    ),
    otp: str = Body(
        ...,
        embed=True,
        description="The OTP sent to the user's email address for password reset verification.",
        title="OTP",
        alias="otp",
    ),
    new_password: str = Body(
        ...,
        embed=True,
        description="The new password to set for the user's account.",
        title="New Password",
        alias="new_password",
    ),
) -> JSONResponse:
    normalized_email_result = await email_normalizer.normalize(email_address)
    normalized_email_address = normalized_email_result.cleaned_email

    credentials = await credentials_collection.find_one(
        {
            "$or": [
                {"email_address_normalized": normalized_email_address},
                {"email_address": email_address},
            ],
            "account_status": AccountStatus.ACTIVE.value,
        }
    )
    if credentials is None:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="No account found with that email address.")

    user_id = credentials["_id"]  # pyright: ignore[reportTypedDictNotRequiredAccess]
    stored_otp = await redis_client.get(f"forget_password_otp:{user_id}")
    if stored_otp is None or stored_otp != otp:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP.")

    await credentials_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "password_hash": _hash_password(new_password),
                "password_algo": PasswordAlgorithm.BCRYPT,
                "updated_at_timestamp": arrow.utcnow().timestamp(),
            },
        },
    )

    await redis_client.delete(f"forget_password_otp:{user_id}")

    refresh_token = await auth_manager.create_or_get_refresh_token(user_id)
    await auth_manager.logout(refresh_token)

    return _create_json_response(detail="Password reset successfully.")
