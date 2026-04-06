from __future__ import annotations

import inspect

import arrow
import orjson
import psutil
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from redis.asyncio import Redis

from src.app import app
from src.models import UserDict
from src.routes.api.v1.meta import extract_mongo_metadata, extract_redis_metadata
from src.utils.metrics import collect_runtime_metrics

database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
mongo_client: AsyncMongoClient = app.state.mongo_client
templates: Jinja2Templates = app.state.templates

users_collection: Collection[UserDict] = database["users"]

router = APIRouter()


@router.get("/dashboard", name="admin_dashboard", include_in_schema=False)
async def admin_dashboard(request: Request, duration_sec: int = Query(300)):
    collection_names = await database.list_collection_names()

    collections = []
    total_documents = 0
    for collection_name in sorted(collection_names):
        col = database[collection_name]
        count = await col.count_documents({})
        collections.append({"name": collection_name, "count": count})
        total_documents += count

    total_users = await users_collection.count_documents({})
    recent_users_cursor = users_collection.find({}).limit(8)
    recent_users = await recent_users_cursor.to_list(length=8)

    top_collections = sorted(collections, key=lambda item: item["count"], reverse=True)[:8]

    redis_info: dict = {"available": False, "dbsize": 0, "connected_clients": 0, "used_memory_human": "-"}
    try:
        ping_result = redis_client.ping()
        if inspect.isawaitable(ping_result):
            ping_result = await ping_result
        info = await redis_client.info()
        redis_info = {
            "available": True,
            "dbsize": await redis_client.dbsize(),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "-"),
        }
    except Exception:
        pass

    uptime_seconds = int((arrow.utcnow() - app.state.start_time).total_seconds())

    meta_info: dict = {
        "version": app.version,
        "status": "OK",
        "uptime_seconds": uptime_seconds,
        "mongo": {"ok": False},
        "redis": {"ok": False},
    }

    try:
        meta_info["mongo"] = await extract_mongo_metadata(mongo_client)
    except Exception:
        pass

    try:
        meta_info["redis"] = await extract_redis_metadata(redis_client)
    except Exception:
        pass

    redis_stats = meta_info.get("redis", {}).get("stats", {}) if isinstance(meta_info.get("redis"), dict) else {}
    keyspace_hits = int(redis_stats.get("keyspace_hits") or 0)
    keyspace_misses = int(redis_stats.get("keyspace_misses") or 0)
    cache_total = keyspace_hits + keyspace_misses
    cache_hit_ratio = round((keyspace_hits / cache_total) * 100, 2) if cache_total > 0 else None

    runtime_metrics = await collect_runtime_metrics(redis_client, duration_sec)

    virtual_memory = psutil.virtual_memory()
    disk_usage = psutil.disk_usage("/")
    network_usage = psutil.net_io_counters()

    system_metrics = {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "ram_percent": virtual_memory.percent,
        "ram_used": virtual_memory.used,
        "ram_total": virtual_memory.total,
        "disk_percent": disk_usage.percent,
        "disk_used": disk_usage.used,
        "disk_total": disk_usage.total,
        "network_bytes_sent": network_usage.bytes_sent,
        "network_bytes_recv": network_usage.bytes_recv,
        "network_packets_sent": network_usage.packets_sent,
        "network_packets_recv": network_usage.packets_recv,
    }

    meta_mongo_json = orjson.dumps(meta_info.get("mongo", {}), option=orjson.OPT_INDENT_2, default=str).decode("utf-8")
    meta_redis_json = orjson.dumps(meta_info.get("redis", {}), option=orjson.OPT_INDENT_2, default=str).decode("utf-8")

    return templates.TemplateResponse(
        "dashboard.html.jinja",
        {
            "request": request,
            "collections": collections,
            "total_collections": len(collections),
            "total_documents": total_documents,
            "total_users": total_users,
            "recent_users": recent_users,
            "redis_info": redis_info,
            "collection_chart_labels": [item["name"] for item in top_collections],
            "collection_chart_values": [item["count"] for item in top_collections],
            "meta_info": meta_info,
            "requests_per_second": runtime_metrics["requests_per_second"],
            "current_second_rps": runtime_metrics["current_second_rps"],
            "total_requests": runtime_metrics["total_requests"],
            "total_404": runtime_metrics["total_404"],
            "total_500": runtime_metrics["total_500"],
            "total_5xx": runtime_metrics["total_5xx"],
            "cache_hit_ratio": cache_hit_ratio,
            "cache_hits": keyspace_hits,
            "cache_misses": keyspace_misses,
            "system_metrics": system_metrics,
            "endpoint_failures": runtime_metrics["endpoint_failures"],
            "endpoint_traffic": runtime_metrics["endpoint_traffic"],
            "meta_mongo_json": meta_mongo_json,
            "meta_redis_json": meta_redis_json,
            "traffic_duration_sec": runtime_metrics["duration_sec"],
        },
    )


@router.get("/dashboard/metrics-json", name="admin_dashboard_metrics", include_in_schema=False)
async def admin_dashboard_metrics(duration_sec: int = Query(300)):
    metrics = await collect_runtime_metrics(redis_client, duration_sec)
    return JSONResponse(metrics)
