from __future__ import annotations

from math import ceil

import arrow
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import AccountStatus, CredentialsDict, UserDict
from src.models.admin import AdminAuditLogDict, make_audit_log
from src.utils.admin_auth import get_client_ip, mask_sensitive_fields, require_csrf

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

users_collection: Collection[UserDict] = database["users"]
credentials_collection: Collection[CredentialsDict] = database["credentials"]
audit_log_collection: Collection[AdminAuditLogDict] = database["admin_audit_log"]

router = APIRouter()

PAGE_SIZE = 20


@router.get("/users", name="admin_users", include_in_schema=False)
async def admin_users(request: Request, page: int = Query(1, ge=1), q: str | None = Query(None)):
    filter_query: dict = {}
    if q:
        filter_query["$or"] = [
            {"_id": q},
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"phone_number": {"$regex": q, "$options": "i"}},
        ]

    total = await users_collection.count_documents(filter_query)
    cursor = users_collection.find(filter_query).sort("created_at_timestamp", -1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    users = await cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "users.html.jinja",
        {
            "request": request,
            "users": users,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "total": total,
        },
    )


@router.post("/users/{user_id}/lock", name="admin_lock_user", include_in_schema=False)
async def admin_lock_user(request: Request, user_id: str):
    require_csrf(request)
    admin_id = request.session.get("admin_id", "")
    admin_username = request.session.get("admin_username", "unknown")
    ip_addr = get_client_ip(request)

    before = await credentials_collection.find_one({"_id": user_id})
    before_masked = mask_sensitive_fields(dict(before)) if before else None

    await credentials_collection.update_one(
        {"_id": user_id},
        {"$set": {"account_status": AccountStatus.LOCKED, "updated_at_timestamp": arrow.utcnow().timestamp()}},
    )

    after = await credentials_collection.find_one({"_id": user_id})
    after_masked = mask_sensitive_fields(dict(after)) if after else None

    log = make_audit_log(
        admin_id=admin_id,
        admin_username=admin_username,
        action="lock_user",
        resource_type="credentials",
        ip_address=ip_addr,
        resource_id=user_id,
        before_state=before_masked,
        after_state=after_masked,
    )
    await audit_log_collection.insert_one(log)

    return JSONResponse({"success": True, "message": f"User {user_id} locked."})


@router.post("/users/{user_id}/unlock", name="admin_unlock_user", include_in_schema=False)
async def admin_unlock_user(request: Request, user_id: str):
    require_csrf(request)
    admin_id = request.session.get("admin_id", "")
    admin_username = request.session.get("admin_username", "unknown")
    ip_addr = get_client_ip(request)

    before = await credentials_collection.find_one({"_id": user_id})
    before_masked = mask_sensitive_fields(dict(before)) if before else None

    await credentials_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "account_status": AccountStatus.ACTIVE,
                "failed_login_attempts": 0,
                "locked_until_timestamp": None,
                "updated_at_timestamp": arrow.utcnow().timestamp(),
            }
        },
    )

    after = await credentials_collection.find_one({"_id": user_id})
    after_masked = mask_sensitive_fields(dict(after)) if after else None

    log = make_audit_log(
        admin_id=admin_id,
        admin_username=admin_username,
        action="unlock_user",
        resource_type="credentials",
        ip_address=ip_addr,
        resource_id=user_id,
        before_state=before_masked,
        after_state=after_masked,
    )
    await audit_log_collection.insert_one(log)

    return JSONResponse({"success": True, "message": f"User {user_id} unlocked."})


@router.get("/users/{user_id}/activity", name="admin_user_activity", include_in_schema=False)
async def admin_user_activity(request: Request, user_id: str):
    user = await users_collection.find_one({"_id": user_id})
    creds = await credentials_collection.find_one({"_id": user_id})

    return templates.TemplateResponse(
        "user_activity.html.jinja",
        {
            "request": request,
            "user": user,
            "credentials": mask_sensitive_fields(dict(creds)) if creds else {},
            "user_id": user_id,
        },
    )
