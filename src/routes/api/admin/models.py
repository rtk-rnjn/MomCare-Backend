from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pymongo.asynchronous.collection import AsyncCollection

from src.app import app
from src.utils.admin_auth import AdminAccessPayload, get_client_ip, require_admin
from src.utils.audit_logger import AuditLogger

router = APIRouter(prefix="/models", tags=["Admin Model Management"])

db = app.state.mongo_database
exercises_collection: AsyncCollection = db["exercises"]
foods_collection: AsyncCollection = db["foods"]
songs_collection: AsyncCollection = db["songs"]
audit_collection: AsyncCollection = db["audit_logs"]
audit_logger = AuditLogger(audit_collection)

COLLECTION_MAP = {
    "exercises": exercises_collection,
    "foods": foods_collection,
    "songs": songs_collection,
}

VALID_COLLECTIONS = set(COLLECTION_MAP.keys())


def _get_collection(collection_name: str) -> AsyncCollection:
    if collection_name not in VALID_COLLECTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid collection. Must be one of: {', '.join(VALID_COLLECTIONS)}")
    return COLLECTION_MAP[collection_name]


@router.get("/{collection_name}")
async def list_items(
    collection_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    admin: AdminAccessPayload = Depends(require_admin),
):
    collection = _get_collection(collection_name)
    query: dict = {}
    if search:
        query["name"] = {"$regex": search, "$options": "i"}

    total = await collection.count_documents(query)
    skip = (page - 1) * per_page
    cursor = collection.find(query).skip(skip).limit(per_page)
    items = await cursor.to_list(length=per_page)

    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.get("/{collection_name}/{item_id}")
async def get_item(
    collection_name: str,
    item_id: str,
    admin: AdminAccessPayload = Depends(require_admin),
):
    collection = _get_collection(collection_name)
    item = await collection.find_one({"_id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/{collection_name}")
async def create_item(
    collection_name: str,
    request: Request,
    data: dict = Body(...),
    admin: AdminAccessPayload = Depends(require_admin),
):
    collection = _get_collection(collection_name)

    if "_id" not in data:
        data["_id"] = str(uuid.uuid4())

    await collection.insert_one(data)

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action=f"create_{collection_name}_item",
        target_type=collection_name,
        target_id=data["_id"],
        after_data=data,
        ip_address=get_client_ip(request),
    )

    return data


@router.put("/{collection_name}/{item_id}")
async def update_item(
    collection_name: str,
    item_id: str,
    request: Request,
    data: dict = Body(...),
    admin: AdminAccessPayload = Depends(require_admin),
):
    collection = _get_collection(collection_name)
    existing = await collection.find_one({"_id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")

    data.pop("_id", None)
    await collection.update_one({"_id": item_id}, {"$set": data})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action=f"update_{collection_name}_item",
        target_type=collection_name,
        target_id=item_id,
        before_data=existing,
        after_data=data,
        ip_address=get_client_ip(request),
    )

    return {"detail": "Item updated"}


@router.delete("/{collection_name}/{item_id}")
async def delete_item(
    collection_name: str,
    item_id: str,
    request: Request,
    admin: AdminAccessPayload = Depends(require_admin),
):
    collection = _get_collection(collection_name)
    existing = await collection.find_one({"_id": item_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")

    await collection.delete_one({"_id": item_id})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action=f"delete_{collection_name}_item",
        target_type=collection_name,
        target_id=item_id,
        before_data=existing,
        ip_address=get_client_ip(request),
    )

    return {"detail": "Item deleted"}


@router.post("/{collection_name}/bulk-delete")
async def bulk_delete(
    collection_name: str,
    request: Request,
    ids: list[str] = Body(..., embed=True),
    admin: AdminAccessPayload = Depends(require_admin),
):
    collection = _get_collection(collection_name)

    result = await collection.delete_many({"_id": {"$in": ids}})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action=f"bulk_delete_{collection_name}",
        target_type=collection_name,
        metadata={"deleted_ids": ids, "deleted_count": result.deleted_count},
        ip_address=get_client_ip(request),
    )

    return {"detail": f"Deleted {result.deleted_count} items", "deleted_count": result.deleted_count}
