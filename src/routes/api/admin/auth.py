from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.asynchronous.collection import AsyncCollection
from redis.asyncio import Redis

from src.app import app
from src.models.admin import AdminLoginRequest
from src.utils.admin_auth import (
    AdminAccessPayload,
    AdminTokenPair,
    create_admin_access_token,
    create_admin_refresh_token,
    decode_admin_token,
    get_client_ip,
    get_current_admin,
    verify_password,
)
from src.utils.audit_logger import AuditLogger

router = APIRouter(prefix="/auth", tags=["Admin Auth"])

db = app.state.mongo_database
admin_collection: AsyncCollection = db["admin_users"]
audit_collection: AsyncCollection = db["audit_logs"]
redis_client: Redis = app.state.redis_client
audit_logger = AuditLogger(audit_collection)

ADMIN_REFRESH_PREFIX = "admin_refresh"
ADMIN_REFRESH_SET_PREFIX = "admin_refresh_set"
ADMIN_REFRESH_TTL = 86400  # 1 day


@router.post("/login", response_model=None)
async def admin_login(body: AdminLoginRequest, request: Request) -> AdminTokenPair:
    admin = await admin_collection.find_one({"username": body.username})
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not admin.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is disabled")

    if not verify_password(body.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    admin_id = str(admin["_id"])
    access_token = create_admin_access_token(admin_id, admin["username"], admin["role"])
    refresh_token, jti = create_admin_refresh_token(admin_id)

    # Store refresh session in Redis
    refresh_key = f"{ADMIN_REFRESH_PREFIX}:{jti}"
    set_key = f"{ADMIN_REFRESH_SET_PREFIX}:{admin_id}"
    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.setex(refresh_key, ADMIN_REFRESH_TTL, admin_id)
        pipe.sadd(set_key, jti)
        pipe.expire(set_key, ADMIN_REFRESH_TTL)
        await pipe.execute()

    # Update last login
    await admin_collection.update_one({"_id": admin_id}, {"$set": {"last_login_timestamp": time.time()}})

    await audit_logger.log(
        admin_id=admin_id,
        admin_username=admin["username"],
        action="admin_login",
        target_type="admin",
        target_id=admin_id,
        ip_address=get_client_ip(request),
    )

    exp_timestamp = int(time.time() + 7200)  # 2 hours
    return AdminTokenPair(access_token=access_token, refresh_token=refresh_token, expires_at_timestamp=exp_timestamp)


@router.post("/refresh", response_model=None)
async def admin_refresh(request: Request) -> AdminTokenPair:
    body = await request.json()
    refresh_token = body.get("refresh_token", "")

    payload = decode_admin_token(refresh_token, "admin_refresh")
    admin_id = payload["sub"]
    old_jti = payload["jti"]

    old_key = f"{ADMIN_REFRESH_PREFIX}:{old_jti}"
    stored = await redis_client.get(old_key)
    if stored is None:
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")

    admin = await admin_collection.find_one({"_id": admin_id})
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")

    new_access = create_admin_access_token(admin_id, admin["username"], admin["role"])
    new_refresh, new_jti = create_admin_refresh_token(admin_id)

    new_key = f"{ADMIN_REFRESH_PREFIX}:{new_jti}"
    set_key = f"{ADMIN_REFRESH_SET_PREFIX}:{admin_id}"

    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.delete(old_key)
        pipe.srem(set_key, old_jti)
        pipe.setex(new_key, ADMIN_REFRESH_TTL, admin_id)
        pipe.sadd(set_key, new_jti)
        pipe.expire(set_key, ADMIN_REFRESH_TTL)
        await pipe.execute()

    exp_timestamp = int(time.time() + 7200)
    return AdminTokenPair(access_token=new_access, refresh_token=new_refresh, expires_at_timestamp=exp_timestamp)


@router.post("/logout")
async def admin_logout(request: Request, admin: AdminAccessPayload = Depends(get_current_admin)):
    body = await request.json()
    refresh_token = body.get("refresh_token", "")

    try:
        payload = decode_admin_token(refresh_token, "admin_refresh")
        jti = payload["jti"]
        admin_id = payload["sub"]

        refresh_key = f"{ADMIN_REFRESH_PREFIX}:{jti}"
        set_key = f"{ADMIN_REFRESH_SET_PREFIX}:{admin_id}"

        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.delete(refresh_key)
            pipe.srem(set_key, jti)
            await pipe.execute()
    except Exception:
        pass

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="admin_logout",
        target_type="admin",
        target_id=admin["sub"],
        ip_address=get_client_ip(request),
    )

    return {"detail": "Logged out successfully"}


@router.get("/me")
async def admin_me(admin: AdminAccessPayload = Depends(get_current_admin)):
    admin_doc = await admin_collection.find_one({"_id": admin["sub"]})
    if not admin_doc:
        raise HTTPException(status_code=404, detail="Admin not found")

    admin_doc.pop("password_hash", None)
    return admin_doc
