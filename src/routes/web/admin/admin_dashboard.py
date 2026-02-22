from __future__ import annotations

import inspect
import time

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

database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
mongo_client: AsyncMongoClient = app.state.mongo_client
templates: Jinja2Templates = app.state.templates

users_collection: Collection[UserDict] = database["users"]

router = APIRouter()


def _decode_text(value) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _normalize_duration(duration_sec: int) -> int:
    if duration_sec < 60:
        return 60
    if duration_sec > 3600:
        return 3600
    return duration_sec


async def _collect_runtime_metrics(duration_sec: int) -> dict:
    duration_sec = _normalize_duration(duration_sec)

    requests_per_second = 0.0
    current_second_rps = 0
    total_requests = 0
    total_404 = 0
    total_500 = 0
    total_5xx = 0
    endpoint_failures = []
    endpoint_traffic = []


    now_second = int(time.time())
    rps_keys = [f"metrics:requests:sec:{ts}" for ts in range(now_second - duration_sec + 1, now_second + 1)]
    rps_values = await redis_client.mget(rps_keys)
    rps_series = [int(value or 0) for value in rps_values]

    requests_in_window = sum(rps_series)
    requests_per_second = round(requests_in_window / duration_sec, 2)
    current_second_rps = rps_series[-1] if rps_series else 0

    total_requests = int(await redis_client.get("metrics:requests:total") or 0)
    total_404 = int(await redis_client.get("metrics:status:404") or 0)
    total_500 = int(await redis_client.get("metrics:status:500") or 0)
    total_5xx = int(await redis_client.get("metrics:status:5xx") or 0)

    endpoint_failure_counts = redis_client.hgetall("metrics:endpoint_failures")
    endpoint_last_errors = redis_client.hgetall("metrics:endpoint_last_error")

    if inspect.isawaitable(endpoint_failure_counts):
        endpoint_failure_counts = await endpoint_failure_counts

    if inspect.isawaitable(endpoint_last_errors):
        endpoint_last_errors = await endpoint_last_errors

    sorted_failures = sorted(
        endpoint_failure_counts.items(),
        key=lambda item: int(item[1]),
        reverse=True,
    )[:20]

    for endpoint, count in sorted_failures:
        endpoint_name = _decode_text(endpoint)
        last_error_raw = endpoint_last_errors.get(endpoint) or endpoint_last_errors.get(endpoint_name)
        last_error = None
        if last_error_raw:
            try:
                last_error = orjson.loads(last_error_raw if isinstance(last_error_raw, bytes) else last_error_raw.encode("utf-8"))
            except Exception:
                last_error = {"message": _decode_text(last_error_raw)}

        endpoint_failures.append({"endpoint": endpoint_name, "count": int(count), "last_error": last_error})

    sec_keys = [f"metrics:endpoint_status:sec:{ts}" for ts in range(now_second - duration_sec + 1, now_second + 1)]
    pipe = redis_client.pipeline()
    for sec_key in sec_keys:
        pipe.hgetall(sec_key)
    sec_hashes = await pipe.execute()

    endpoint_breakdown: dict[str, dict[str, int]] = {}
    for sec_hash in sec_hashes:
        for endpoint_status_key, raw_count in sec_hash.items():
            key_text = _decode_text(endpoint_status_key)
            if "|" not in key_text:
                continue

            endpoint_name, status_text = key_text.rsplit("|", 1)
            try:
                status_code = int(status_text)
                count = int(raw_count)
            except Exception:
                continue

            if endpoint_name not in endpoint_breakdown:
                endpoint_breakdown[endpoint_name] = {"count": 0, "2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}

            endpoint_breakdown[endpoint_name]["count"] += count
            if 200 <= status_code < 300:
                endpoint_breakdown[endpoint_name]["2xx"] += count
            elif 300 <= status_code < 400:
                endpoint_breakdown[endpoint_name]["3xx"] += count
            elif 400 <= status_code < 500:
                endpoint_breakdown[endpoint_name]["4xx"] += count
            elif 500 <= status_code < 600:
                endpoint_breakdown[endpoint_name]["5xx"] += count

    endpoint_traffic = []

    def parse_last_error(endpoint_name: str, endpoint_last_errors: dict):
        raw = endpoint_last_errors.get(endpoint_name) or endpoint_last_errors.get(endpoint_name.encode("utf-8"))

        if not raw:
            return None

        if isinstance(raw, bytes):
            return orjson.loads(raw)

        return orjson.loads(str(raw).encode("utf-8"))

    for endpoint_name, values in endpoint_breakdown.items():
        endpoint_traffic.append(
            {
                "endpoint": endpoint_name,
                "count": values["count"],
                "2xx": values["2xx"],
                "3xx": values["3xx"],
                "4xx": values["4xx"],
                "5xx": values["5xx"],
                "last_error": parse_last_error(endpoint_name, endpoint_last_errors),
            }
        )

    endpoint_traffic = sorted(
        endpoint_traffic,
        key=lambda item: item["count"],
        reverse=True,
    )[:30]

    return {
        "duration_sec": duration_sec,
        "requests_per_second": requests_per_second,
        "current_second_rps": current_second_rps,
        "total_requests": total_requests,
        "total_404": total_404,
        "total_500": total_500,
        "total_5xx": total_5xx,
        "endpoint_failures": endpoint_failures,
        "endpoint_traffic": endpoint_traffic,
    }


@router.get("/dashboard", include_in_schema=False)
async def admin_dashboard(request: Request, duration_sec: int = Query(300)):
    collection_names = await database.list_collection_names()

    collections = []
    total_documents = 0
    for collection_name in sorted(collection_names):
        collection = database[collection_name]
        count = await collection.count_documents({})
        collections.append({"name": collection_name, "count": count})
        total_documents += count

    total_users = await users_collection.count_documents({})
    recent_users_cursor = users_collection.find({}).limit(8)
    recent_users = await recent_users_cursor.to_list(length=8)

    top_collections = sorted(collections, key=lambda item: item["count"], reverse=True)[:8]

    redis_info: dict = {
        "available": False,
        "dbsize": 0,
        "connected_clients": 0,
        "used_memory_human": "-",
    }
    try:
        maybe_awaitable = redis_client.ping()
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable
        info = await redis_client.info()
        redis_info = {
            "available": maybe_awaitable is True,
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

    runtime_metrics = await _collect_runtime_metrics(duration_sec)
    requests_per_second = runtime_metrics["requests_per_second"]
    current_second_rps = runtime_metrics["current_second_rps"]
    total_requests = runtime_metrics["total_requests"]
    total_404 = runtime_metrics["total_404"]
    total_500 = runtime_metrics["total_500"]
    total_5xx = runtime_metrics["total_5xx"]
    endpoint_failures = runtime_metrics["endpoint_failures"]
    endpoint_traffic = runtime_metrics["endpoint_traffic"]

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
            "requests_per_second": requests_per_second,
            "current_second_rps": current_second_rps,
            "total_requests": total_requests,
            "total_404": total_404,
            "total_500": total_500,
            "total_5xx": total_5xx,
            "cache_hit_ratio": cache_hit_ratio,
            "cache_hits": keyspace_hits,
            "cache_misses": keyspace_misses,
            "system_metrics": system_metrics,
            "endpoint_failures": endpoint_failures,
            "endpoint_traffic": endpoint_traffic,
            "meta_mongo_json": meta_mongo_json,
            "meta_redis_json": meta_redis_json,
            "traffic_duration_sec": runtime_metrics["duration_sec"],
        },
    )


@router.get("/dashboard/metrics", include_in_schema=False)
async def admin_dashboard_metrics(duration_sec: int = Query(300)):
    metrics = await _collect_runtime_metrics(duration_sec)
    return JSONResponse(metrics)
