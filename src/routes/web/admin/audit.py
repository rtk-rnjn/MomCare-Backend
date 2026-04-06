from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models.admin import AdminAuditLogDict, AdminLoginAttemptDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

audit_log_collection: Collection[AdminAuditLogDict] = database["admin_audit_log"]
login_attempts_collection: Collection[AdminLoginAttemptDict] = database["admin_login_attempts"]

router = APIRouter()

PAGE_SIZE = 30


@router.get("/audit-log", name="admin_audit_log", include_in_schema=False)
async def admin_audit_log(
    request: Request,
    page: int = Query(1, ge=1),
    admin_username: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
):
    filter_query: dict = {}
    if admin_username:
        filter_query["admin_username"] = {"$regex": admin_username, "$options": "i"}
    if action:
        filter_query["action"] = {"$regex": action, "$options": "i"}
    if resource_type:
        filter_query["resource_type"] = resource_type

    total = await audit_log_collection.count_documents(filter_query)
    cursor = audit_log_collection.find(filter_query).sort("timestamp", -1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    logs = await cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "audit_log.html.jinja",
        {
            "request": request,
            "logs": logs,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "admin_username": admin_username or "",
            "action": action or "",
            "resource_type": resource_type or "",
        },
    )


@router.get("/login-attempts", name="admin_login_attempts", include_in_schema=False)
async def admin_login_attempts_view(
    request: Request,
    page: int = Query(1, ge=1),
    username: str | None = Query(None),
    success: str | None = Query(None),
):
    filter_query: dict = {}
    if username:
        filter_query["username"] = {"$regex": username, "$options": "i"}
    if success is not None and success != "":
        filter_query["success"] = success.lower() == "true"

    total = await login_attempts_collection.count_documents(filter_query)
    cursor = login_attempts_collection.find(filter_query).sort("timestamp", -1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    attempts = await cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "login_attempts.html.jinja",
        {
            "request": request,
            "attempts": attempts,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "username": username or "",
            "success": success or "",
        },
    )
