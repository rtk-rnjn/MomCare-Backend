from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.asynchronous.collection import AsyncCollection

from src.app import app
from src.models.user import AccountStatus
from src.utils.admin_auth import AdminAccessPayload, get_client_ip, require_admin
from src.utils.audit_logger import AuditLogger

router = APIRouter(prefix="/users", tags=["Admin User Management"])

db = app.state.mongo_database
users_collection: AsyncCollection = db["users"]
credentials_collection: AsyncCollection = db["credentials"]
audit_collection: AsyncCollection = db["audit_logs"]
audit_logger = AuditLogger(audit_collection)


@router.get("/")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    status: str | None = Query(None),
    sort_by: str = Query("created_at_timestamp"),
    sort_dir: int = Query(-1, ge=-1, le=1),
    admin: AdminAccessPayload = Depends(require_admin),
):
    query: dict = {}
    cred_query: dict = {}

    if status:
        cred_query["account_status"] = status

    if search:
        escaped_search = re.escape(search)
        query["$or"] = [
            {"first_name": {"$regex": escaped_search, "$options": "i"}},
            {"last_name": {"$regex": escaped_search, "$options": "i"}},
        ]
        # Also search credentials by email
        cred_query_search = {"email_address": {"$regex": escaped_search, "$options": "i"}}
        if cred_query:
            cred_query = {"$and": [cred_query, cred_query_search]}
        else:
            cred_query = cred_query_search

    # Get credential IDs matching filters
    user_ids = None
    if cred_query:
        cred_cursor = credentials_collection.find(cred_query, {"_id": 1})
        cred_docs = await cred_cursor.to_list(length=10000)
        user_ids = [str(doc["_id"]) for doc in cred_docs]
        if user_ids:
            if query:
                query = {"$and": [query, {"_id": {"$in": user_ids}}]}
            else:
                query["_id"] = {"$in": user_ids}
        else:
            # No matching credentials found, return empty results
            query["_id"] = {"$in": []}

    total = await users_collection.count_documents(query)
    skip = (page - 1) * per_page
    sort_direction = sort_dir if sort_dir != 0 else -1

    cursor = users_collection.find(query).skip(skip).limit(per_page).sort(sort_by, sort_direction)
    users = await cursor.to_list(length=per_page)

    # Enrich with credential info
    for user in users:
        cred = await credentials_collection.find_one({"_id": user["_id"]}, {"password_hash": 0, "password_algo": 0})
        if cred:
            user["email_address"] = cred.get("email_address")
            user["account_status"] = cred.get("account_status", "ACTIVE")
            user["verified_email"] = cred.get("verified_email", False)

    return {"items": users, "total": total, "page": page, "per_page": per_page}


@router.get("/{user_id}")
async def get_user(user_id: str, admin: AdminAccessPayload = Depends(require_admin)):
    user = await users_collection.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    cred = await credentials_collection.find_one({"_id": user_id}, {"password_hash": 0, "password_algo": 0})
    if cred:
        user["email_address"] = cred.get("email_address")
        user["account_status"] = cred.get("account_status", "ACTIVE")
        user["verified_email"] = cred.get("verified_email", False)
        user["authentication_providers"] = cred.get("authentication_providers", [])
        user["created_at_timestamp"] = cred.get("created_at_timestamp")
        user["last_login_timestamp"] = cred.get("last_login_timestamp")

    return user


@router.post("/{user_id}/lock")
async def lock_user(user_id: str, request: Request, admin: AdminAccessPayload = Depends(require_admin)):
    cred = await credentials_collection.find_one({"_id": user_id})
    if not cred:
        raise HTTPException(status_code=404, detail="User not found")

    current_status = cred.get("account_status", "ACTIVE")
    if current_status == AccountStatus.LOCKED:
        raise HTTPException(status_code=409, detail="User is already locked")

    await credentials_collection.update_one(
        {"_id": user_id},
        {"$set": {"account_status": AccountStatus.LOCKED, "locked_until_timestamp": None}},
    )

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="lock_user",
        target_type="user",
        target_id=user_id,
        before_data={"account_status": current_status},
        after_data={"account_status": AccountStatus.LOCKED},
        ip_address=get_client_ip(request),
    )

    return {"detail": "User locked"}


@router.post("/{user_id}/unlock")
async def unlock_user(user_id: str, request: Request, admin: AdminAccessPayload = Depends(require_admin)):
    cred = await credentials_collection.find_one({"_id": user_id})
    if not cred:
        raise HTTPException(status_code=404, detail="User not found")

    current_status = cred.get("account_status", "ACTIVE")
    if current_status != AccountStatus.LOCKED:
        raise HTTPException(status_code=409, detail="User is not locked")

    await credentials_collection.update_one(
        {"_id": user_id},
        {"$set": {"account_status": AccountStatus.ACTIVE, "locked_until_timestamp": None, "failed_login_attempts": 0}},
    )

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="unlock_user",
        target_type="user",
        target_id=user_id,
        before_data={"account_status": current_status},
        after_data={"account_status": AccountStatus.ACTIVE},
        ip_address=get_client_ip(request),
    )

    return {"detail": "User unlocked"}


@router.delete("/{user_id}")
async def delete_user(user_id: str, request: Request, admin: AdminAccessPayload = Depends(require_admin)):
    cred = await credentials_collection.find_one({"_id": user_id})
    if not cred:
        raise HTTPException(status_code=404, detail="User not found")

    current_status = cred.get("account_status", "ACTIVE")

    await credentials_collection.update_one({"_id": user_id}, {"$set": {"account_status": AccountStatus.DELETED}})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="delete_user",
        target_type="user",
        target_id=user_id,
        before_data={"account_status": current_status},
        after_data={"account_status": AccountStatus.DELETED},
        ip_address=get_client_ip(request),
    )

    return {"detail": "User deleted (soft)"}
