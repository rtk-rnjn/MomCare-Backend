from __future__ import annotations

from math import ceil
from typing import Any

import arrow
import bcrypt
from fastapi import APIRouter, Body, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models.admin import AdminRole, AdminUserDict, make_admin_user, make_audit_log
from src.utils.admin_auth import get_client_ip, require_csrf

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

admin_users_collection: Collection[AdminUserDict] = database["admin_users"]
audit_log_collection: Any = database["admin_audit_log"]

router = APIRouter()

PAGE_SIZE = 20


def _require_super_admin(request: Request) -> None:
    if request.session.get("admin_role") != AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super-admin access required.")


@router.get("/accounts", name="admin_accounts", include_in_schema=False)
async def admin_accounts(request: Request, page: int = Query(1, ge=1)):
    _require_super_admin(request)
    total = await admin_users_collection.count_documents({})
    cursor = admin_users_collection.find({}, {"password_hash": 0}).sort("created_at_timestamp", -1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    admins = await cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))
    return templates.TemplateResponse("admin_accounts.html.jinja", {
        "request": request,
        "admins": admins,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "roles": [r.value for r in AdminRole],
    })


@router.post("/accounts/create", name="admin_create_account", include_in_schema=False)
async def admin_create_account(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    role: str = Form(default=AdminRole.OPERATOR),
):
    _require_super_admin(request)
    require_csrf(request)

    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")

    existing = await admin_users_collection.find_one({"username": username})
    if existing:
        raise HTTPException(status_code=409, detail=f"Admin with username '{username}' already exists.")

    try:
        admin_role = AdminRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role!r}")

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    new_admin = make_admin_user(username=username, password_hash=password_hash, display_name=display_name, role=admin_role)
    await admin_users_collection.insert_one(new_admin)

    log = make_audit_log(
        admin_id=request.session.get("admin_id", ""),
        admin_username=request.session.get("admin_username", "unknown"),
        action="create_admin",
        resource_type="admin_users",
        ip_address=get_client_ip(request),
        resource_id=new_admin["_id"],
        details=f"Created admin '{username}' with role '{admin_role}'",
    )
    await audit_log_collection.insert_one(log)

    return RedirectResponse(url=request.url_for("admin_accounts"), status_code=303)


@router.post("/accounts/{admin_id}/deactivate", name="admin_deactivate_account", include_in_schema=False)
async def admin_deactivate_account(request: Request, admin_id: str):
    _require_super_admin(request)
    require_csrf(request)

    if admin_id == request.session.get("admin_id"):
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account.")

    result = await admin_users_collection.update_one(
        {"_id": admin_id},
        {"$set": {"is_active": False, "updated_at_timestamp": arrow.utcnow().timestamp()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Admin not found.")

    log = make_audit_log(
        admin_id=request.session.get("admin_id", ""),
        admin_username=request.session.get("admin_username", "unknown"),
        action="deactivate_admin",
        resource_type="admin_users",
        ip_address=get_client_ip(request),
        resource_id=admin_id,
    )
    await audit_log_collection.insert_one(log)

    return JSONResponse({"ok": True})


@router.post("/accounts/{admin_id}/activate", name="admin_activate_account", include_in_schema=False)
async def admin_activate_account(request: Request, admin_id: str):
    _require_super_admin(request)
    require_csrf(request)

    result = await admin_users_collection.update_one(
        {"_id": admin_id},
        {"$set": {"is_active": True, "updated_at_timestamp": arrow.utcnow().timestamp()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Admin not found.")

    log = make_audit_log(
        admin_id=request.session.get("admin_id", ""),
        admin_username=request.session.get("admin_username", "unknown"),
        action="activate_admin",
        resource_type="admin_users",
        ip_address=get_client_ip(request),
        resource_id=admin_id,
    )
    await audit_log_collection.insert_one(log)

    return JSONResponse({"ok": True})


@router.post("/accounts/{admin_id}/rotate-password", name="admin_rotate_password", include_in_schema=False)
async def admin_rotate_password(request: Request, admin_id: str, payload: dict = Body(...)):
    _require_super_admin(request)
    require_csrf(request)

    new_password = str(payload.get("new_password", "")).strip()
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    result = await admin_users_collection.update_one(
        {"_id": admin_id},
        {"$set": {"password_hash": password_hash, "updated_at_timestamp": arrow.utcnow().timestamp()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Admin not found.")

    log = make_audit_log(
        admin_id=request.session.get("admin_id", ""),
        admin_username=request.session.get("admin_username", "unknown"),
        action="rotate_password",
        resource_type="admin_users",
        ip_address=get_client_ip(request),
        resource_id=admin_id,
    )
    await audit_log_collection.insert_one(log)

    return JSONResponse({"ok": True})
