from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pymongo.asynchronous.collection import AsyncCollection
from redis.asyncio import Redis

from src.app import app
from src.utils.admin_auth import AdminAccessPayload, get_client_ip, require_admin
from src.utils.audit_logger import AuditLogger
from src.utils.redis_cli_executor import RedisCliExecutor

router = APIRouter(prefix="/db", tags=["Admin DB Tools"])

db = app.state.mongo_database
redis_client: Redis = app.state.redis_client
audit_collection: AsyncCollection = db["audit_logs"]
audit_logger = AuditLogger(audit_collection)
redis_executor = RedisCliExecutor(redis_client)


# ---- Redis Tools ----


@router.post("/redis/execute")
async def redis_execute(
    request: Request,
    command: str = Body(..., embed=True),
    admin: AdminAccessPayload = Depends(require_admin),
):
    result = await redis_executor.execute_command(command)

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="redis_execute",
        target_type="redis",
        metadata={"command": command, "success": result["success"]},
        ip_address=get_client_ip(request),
    )

    return result


@router.get("/redis/allowed-commands")
async def redis_allowed_commands(admin: AdminAccessPayload = Depends(require_admin)):
    return {
        "allowed": redis_executor.get_allowed_commands(),
        "forbidden": sorted(list(redis_executor.FORBIDDEN_COMMANDS)),
    }


@router.get("/redis/info")
async def redis_info(admin: AdminAccessPayload = Depends(require_admin)):
    try:
        info = await redis_client.info()
        return {
            "connected": True,
            "version": info.get("redis_version", "unknown"),
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "connected_clients": info.get("connected_clients", 0),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            "db_size": await redis_client.dbsize(),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


# ---- MongoDB Tools ----


@router.get("/mongo/collections")
async def mongo_collections(admin: AdminAccessPayload = Depends(require_admin)):
    collections = await db.list_collection_names()
    result = []
    for name in sorted(collections):
        count = await db[name].estimated_document_count()
        result.append({"name": name, "document_count": count})
    return result


@router.get("/mongo/collections/{collection_name}")
async def mongo_browse(
    collection_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    admin: AdminAccessPayload = Depends(require_admin),
):
    collections = await db.list_collection_names()
    if collection_name not in collections:
        raise HTTPException(status_code=404, detail="Collection not found")

    collection = db[collection_name]
    total = await collection.estimated_document_count()
    skip = (page - 1) * per_page
    cursor = collection.find({}).skip(skip).limit(per_page)
    docs = await cursor.to_list(length=per_page)

    return {"items": docs, "total": total, "page": page, "per_page": per_page, "collection": collection_name}


@router.get("/mongo/collections/{collection_name}/{doc_id}")
async def mongo_get_document(
    collection_name: str,
    doc_id: str,
    admin: AdminAccessPayload = Depends(require_admin),
):
    collections = await db.list_collection_names()
    if collection_name not in collections:
        raise HTTPException(status_code=404, detail="Collection not found")

    doc = await db[collection_name].find_one({"_id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/mongo/collections/{collection_name}/{doc_id}")
async def mongo_delete_document(
    collection_name: str,
    doc_id: str,
    request: Request,
    admin: AdminAccessPayload = Depends(require_admin),
):
    collections = await db.list_collection_names()
    if collection_name not in collections:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Prevent deletion from admin_users and audit_logs through this endpoint
    if collection_name in ("admin_users", "audit_logs"):
        raise HTTPException(status_code=403, detail=f"Cannot delete from {collection_name} through DB tools")

    doc = await db[collection_name].find_one({"_id": doc_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db[collection_name].delete_one({"_id": doc_id})

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="mongo_delete_document",
        target_type=collection_name,
        target_id=doc_id,
        before_data=doc,
        ip_address=get_client_ip(request),
    )

    return {"detail": "Document deleted"}


@router.get("/mongo/stats")
async def mongo_stats(admin: AdminAccessPayload = Depends(require_admin)):
    try:
        stats = await db.command("dbStats")
        return {
            "connected": True,
            "db_name": db.name,
            "collections": stats.get("collections", 0),
            "data_size": stats.get("dataSize", 0),
            "storage_size": stats.get("storageSize", 0),
            "indexes": stats.get("indexes", 0),
            "objects": stats.get("objects", 0),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
