from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.asynchronous.collection import AsyncCollection

from src.app import app
from src.models.admin import AdminCreateRequest, AdminRole, AdminUpdateRequest
from src.utils.admin_auth import AdminAccessPayload, get_client_ip, hash_password, require_super_admin
from src.utils.audit_logger import AuditLogger

router = APIRouter(prefix="/admins", tags=["Admin Management"])

db = app.state.mongo_database
admin_collection: AsyncCollection = db["admin_users"]
audit_collection: AsyncCollection = db["audit_logs"]
audit_logger = AuditLogger(audit_collection)


@router.get("/")
async def list_admins(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin: AdminAccessPayload = Depends(require_super_admin),
):
    skip = (page - 1) * per_page
    total = await admin_collection.count_documents({})
    cursor = admin_collection.find({}, {"password_hash": 0}).skip(skip).limit(per_page).sort("created_at_timestamp", -1)
    admins = await cursor.to_list(length=per_page)
    return {"items": admins, "total": total, "page": page, "per_page": per_page}


@router.post("/")
async def create_admin(
    body: AdminCreateRequest,
    request: Request,
    admin: AdminAccessPayload = Depends(require_super_admin),
):
    existing = await admin_collection.find_one({"username": body.username})
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    import uuid

    now = time.time()
    admin_doc = {
        "_id": str(uuid.uuid4()),
        "username": body.username,
        "password_hash": hash_password(body.password),
        "role": AdminRole.ADMIN,
        "is_active": True,
        "created_at_timestamp": now,
        "updated_at_timestamp": now,
        "created_by": admin["sub"],
    }

    await admin_collection.insert_one(admin_doc)

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="create_admin",
        target_type="admin",
        target_id=admin_doc["_id"],
        after_data={"username": body.username, "role": AdminRole.ADMIN},
        ip_address=get_client_ip(request),
    )

    admin_doc.pop("password_hash", None)
    return admin_doc


@router.get("/{admin_id}")
async def get_admin(admin_id: str, admin: AdminAccessPayload = Depends(require_super_admin)):
    doc = await admin_collection.find_one({"_id": admin_id}, {"password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Admin not found")
    return doc


@router.patch("/{admin_id}")
async def update_admin(
    admin_id: str,
    body: AdminUpdateRequest,
    request: Request,
    admin: AdminAccessPayload = Depends(require_super_admin),
):
    target = await admin_collection.find_one({"_id": admin_id})
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found")

    if target["role"] == AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot modify super admin")

    updates: dict = {"updated_at_timestamp": time.time()}
    before_data = {}
    after_data = {}

    if body.is_active is not None:
        before_data["is_active"] = target.get("is_active")
        updates["is_active"] = body.is_active
        after_data["is_active"] = body.is_active

    if body.password is not None:
        updates["password_hash"] = hash_password(body.password)
        after_data["password_changed"] = True

    await admin_collection.update_one({"_id": admin_id}, {"$set": updates})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="update_admin",
        target_type="admin",
        target_id=admin_id,
        before_data=before_data,
        after_data=after_data,
        ip_address=get_client_ip(request),
    )

    return {"detail": "Admin updated"}


@router.delete("/{admin_id}")
async def delete_admin(
    admin_id: str,
    request: Request,
    admin: AdminAccessPayload = Depends(require_super_admin),
):
    target = await admin_collection.find_one({"_id": admin_id})
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found")

    if target["role"] == AdminRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Cannot delete super admin")

    await admin_collection.delete_one({"_id": admin_id})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="delete_admin",
        target_type="admin",
        target_id=admin_id,
        before_data={"username": target["username"]},
        ip_address=get_client_ip(request),
    )

    return {"detail": "Admin deleted"}
