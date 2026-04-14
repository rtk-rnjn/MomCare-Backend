from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from pymongo.asynchronous.collection import AsyncCollection

from src.app import app
from src.utils.admin_auth import AdminAccessPayload, require_admin

router = APIRouter(prefix="/logs", tags=["Admin Log Analytics"])

db = app.state.mongo_database
http_logs_collection: AsyncCollection = db["http_logs"]
audit_collection: AsyncCollection = db["audit_logs"]


@router.get("/analytics")
async def log_analytics(
    start_time: float | None = Query(None),
    end_time: float | None = Query(None),
    admin: AdminAccessPayload = Depends(require_admin),
):
    query: dict = {}
    if start_time is not None or end_time is not None:
        time_filter: dict = {}
        if start_time is not None:
            time_filter["$gte"] = start_time
        if end_time is not None:
            time_filter["$lte"] = end_time
        query["timestamp"] = time_filter

    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": {
                    "category": {
                        "$switch": {
                            "branches": [
                                {"case": {"$and": [{"$gte": ["$status_code", 200]}, {"$lt": ["$status_code", 300]}]}, "then": "2xx"},
                                {"case": {"$and": [{"$gte": ["$status_code", 300]}, {"$lt": ["$status_code", 400]}]}, "then": "3xx"},
                                {"case": {"$and": [{"$gte": ["$status_code", 400]}, {"$lt": ["$status_code", 500]}]}, "then": "4xx"},
                                {"case": {"$and": [{"$gte": ["$status_code", 500]}, {"$lt": ["$status_code", 600]}]}, "then": "5xx"},
                            ],
                            "default": "other",
                        }
                    }
                },
                "count": {"$sum": 1},
                "avg_time": {"$avg": "$process_time_ms"},
            }
        },
    ]

    results = {}
    async for doc in http_logs_collection.aggregate(pipeline):
        cat = doc["_id"]["category"]
        results[cat] = {"count": doc["count"], "avg_time_ms": round(doc.get("avg_time", 0), 2)}

    total = sum(v["count"] for v in results.values())

    return {
        "total_requests": total,
        "categories": results,
        "time_range": {"start": start_time, "end": end_time},
    }


@router.get("/timeline")
async def log_timeline(
    start_time: float | None = Query(None),
    end_time: float | None = Query(None),
    interval: str = Query("hour", pattern="^(minute|hour|day)$"),
    admin: AdminAccessPayload = Depends(require_admin),
):
    query: dict = {}
    if start_time is not None or end_time is not None:
        time_filter: dict = {}
        if start_time is not None:
            time_filter["$gte"] = start_time
        if end_time is not None:
            time_filter["$lte"] = end_time
        query["timestamp"] = time_filter

    # Group by time bucket
    if interval == "minute":
        bucket_size = 60
    elif interval == "hour":
        bucket_size = 3600
    else:
        bucket_size = 86400

    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": {
                    "bucket": {"$subtract": ["$timestamp", {"$mod": ["$timestamp", bucket_size]}]},
                },
                "total": {"$sum": 1},
                "errors": {
                    "$sum": {
                        "$cond": [{"$gte": ["$status_code", 400]}, 1, 0],
                    }
                },
            }
        },
        {"$sort": {"_id.bucket": 1}},
    ]

    data_points = []
    async for doc in http_logs_collection.aggregate(pipeline):
        data_points.append(
            {
                "timestamp": doc["_id"]["bucket"],
                "total": doc["total"],
                "errors": doc["errors"],
            }
        )

    return {"interval": interval, "data": data_points}


@router.get("/errors")
async def log_errors(
    start_time: float | None = Query(None),
    end_time: float | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin: AdminAccessPayload = Depends(require_admin),
):
    query: dict = {"status_code": {"$gte": 400}}
    if start_time is not None or end_time is not None:
        time_filter: dict = {}
        if start_time is not None:
            time_filter["$gte"] = start_time
        if end_time is not None:
            time_filter["$lte"] = end_time
        query["timestamp"] = time_filter

    total = await http_logs_collection.count_documents(query)
    skip = (page - 1) * per_page
    cursor = http_logs_collection.find(query).skip(skip).limit(per_page).sort("timestamp", -1)
    errors = await cursor.to_list(length=per_page)

    return {"items": errors, "total": total, "page": page, "per_page": per_page}


@router.get("/drilldown")
async def log_drilldown(
    status_code: int | None = Query(None),
    method: str | None = Query(None),
    path_prefix: str | None = Query(None),
    start_time: float | None = Query(None),
    end_time: float | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin: AdminAccessPayload = Depends(require_admin),
):
    query: dict = {}
    if status_code is not None:
        query["status_code"] = status_code
    if method is not None:
        query["method"] = method.upper()
    if path_prefix is not None:
        query["path"] = {"$regex": f"^{path_prefix}"}
    if start_time is not None or end_time is not None:
        time_filter: dict = {}
        if start_time is not None:
            time_filter["$gte"] = start_time
        if end_time is not None:
            time_filter["$lte"] = end_time
        query["timestamp"] = time_filter

    total = await http_logs_collection.count_documents(query)
    skip = (page - 1) * per_page
    cursor = http_logs_collection.find(query).skip(skip).limit(per_page).sort("timestamp", -1)
    logs = await cursor.to_list(length=per_page)

    return {"items": logs, "total": total, "page": page, "per_page": per_page}


@router.get("/audit")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    action: str | None = Query(None),
    admin_id: str | None = Query(None),
    admin: AdminAccessPayload = Depends(require_admin),
):
    query: dict = {}
    if action:
        query["action"] = action
    if admin_id:
        query["admin_id"] = admin_id

    total = await audit_collection.count_documents(query)
    skip = (page - 1) * per_page
    cursor = audit_collection.find(query).skip(skip).limit(per_page).sort("timestamp", -1)
    logs = await cursor.to_list(length=per_page)

    return {"items": logs, "total": total, "page": page, "per_page": per_page}
