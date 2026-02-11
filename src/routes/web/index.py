from __future__ import annotations

import asyncio
from time import perf_counter

import arrow
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis

from src.app import app
from src.models import AccountStatus

templates: Jinja2Templates = app.state.templates
database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

credentials_collection: Collection = database["credentials"]
users_collection: Collection = database["users"]

router = APIRouter(include_in_schema=False)


def _format_timestamp(ts: float | None) -> str:
    if not ts:
        return "—"
    return arrow.get(ts).to("local").format("YYYY-MM-DD HH:mm")


def _title_case(value: str | None) -> str:
    if not value:
        return "—"
    return value.replace("_", " ").title()


async def _get_user_counts() -> dict[str, int]:
    pipeline = [
        {"$match": {"account_status": {"$ne": AccountStatus.DELETED}}},
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "active": {"$sum": {"$cond": [{"$eq": ["$account_status", AccountStatus.ACTIVE]}, 1, 0]}},
                "locked": {"$sum": {"$cond": [{"$eq": ["$account_status", AccountStatus.LOCKED]}, 1, 0]}},
                "verified": {"$sum": {"$cond": [{"$eq": ["$verified_email", True]}, 1, 0]}},
            }
        },
    ]
    results = await (await credentials_collection.aggregate(pipeline)).to_list(length=1)
    if not results:
        return {"total": 0, "active": 0, "locked": 0, "verified": 0}
    row = results[0]
    return {
        "total": int(row.get("total", 0)),
        "active": int(row.get("active", 0)),
        "locked": int(row.get("locked", 0)),
        "verified": int(row.get("verified", 0)),
    }


async def _get_provider_counts() -> dict[str, int]:
    pipeline = [
        {"$match": {"account_status": {"$ne": AccountStatus.DELETED}}},
        {"$project": {"providers": {"$ifNull": ["$authentication_providers", []]}}},
        {"$unwind": {"path": "$providers", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": "$providers", "count": {"$sum": 1}}},
    ]
    results = await (await credentials_collection.aggregate(pipeline)).to_list(length=None)
    counts: dict[str, int] = {}
    for row in results:
        key = row.get("_id")
        if not key:
            continue
        counts[str(key).title()] = int(row.get("count", 0))
    if not counts:
        counts["Internal"] = 0
    return counts


async def _get_recent_users(limit: int = 25) -> list[dict[str, str]]:
    pipeline = [
        {"$match": {"account_status": {"$ne": AccountStatus.DELETED}}},
        {"$sort": {"last_login_timestamp": -1, "created_at_timestamp": -1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "_id",
                "as": "user",
            }
        },
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 1,
                "email_address": 1,
                "account_status": 1,
                "verified_email": 1,
                "authentication_providers": 1,
                "last_login_timestamp": 1,
                "user": 1,
            }
        },
    ]
    docs = await (await credentials_collection.aggregate(pipeline)).to_list(length=limit)
    rows: list[dict[str, str]] = []
    for doc in docs:
        user = doc.get("user") or {}
        providers = doc.get("authentication_providers") or []
        provider_label = ", ".join([str(provider).title() for provider in providers]) or "Internal"
        first_name = user.get("first_name") or ""
        last_name = user.get("last_name") or ""
        name = (first_name + " " + last_name).strip() or "—"
        rows.append(
            {
                "id": str(doc.get("_id", "—")),
                "name": name,
                "email": doc.get("email_address") or "—",
                "phone": user.get("phone_number") or "—",
                "provider": provider_label,
                "status": _title_case(doc.get("account_status")),
                "verified": "Yes" if doc.get("verified_email") else "No",
                "last_login": _format_timestamp(doc.get("last_login_timestamp")),
            }
        )
    return rows


async def _get_activity(limit: int = 8) -> list[dict[str, str]]:
    pipeline = [
        {"$match": {"account_status": {"$ne": AccountStatus.DELETED}}},
        {"$sort": {"last_login_timestamp": -1, "created_at_timestamp": -1}},
        {"$limit": limit},
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "_id",
                "as": "user",
            }
        },
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 1,
                "account_status": 1,
                "last_login_timestamp": 1,
                "created_at_timestamp": 1,
                "user": 1,
            }
        },
    ]
    docs = await (await credentials_collection.aggregate(pipeline)).to_list(length=limit)
    activity: list[dict[str, str]] = []
    for doc in docs:
        user = doc.get("user") or {}
        first_name = user.get("first_name") or ""
        last_name = user.get("last_name") or ""
        name = (first_name + " " + last_name).strip() or "—"
        last_login = doc.get("last_login_timestamp")
        created = doc.get("created_at_timestamp")
        timestamp = _format_timestamp(last_login or created)
        action = "Login" if last_login else "Registered"
        status = _title_case(doc.get("account_status"))
        activity.append({"timestamp": timestamp, "user": name, "action": action, "status": status})
    return activity


async def _get_mongo_metrics() -> dict[str, str | int | float | bool]:
    start = perf_counter()
    try:
        await database.command("ping")
        ok = True
    except Exception:
        ok = False
    latency_ms = (perf_counter() - start) * 1000
    try:
        collections = await database.list_collection_names()
    except Exception:
        collections = []
    return {
        "ok": ok,
        "latency_ms": round(latency_ms, 2),
        "collections": len(collections),
    }


async def _get_redis_metrics() -> dict[str, str | int | float | bool]:
    start = perf_counter()
    try:
        await redis_client.ping()
        ok = True
    except Exception:
        ok = False
    latency_ms = (perf_counter() - start) * 1000
    info = {}
    keys = 0
    if ok:
        try:
            info = await redis_client.info()
            keys = int(await redis_client.dbsize())
        except Exception:
            info = {}
            keys = 0
    used_memory = info.get("used_memory_human") or info.get("used_memory") or "—"
    uptime = info.get("uptime_in_seconds")
    return {
        "ok": ok,
        "latency_ms": round(latency_ms, 2),
        "used_memory": used_memory,
        "keys": keys,
        "uptime_seconds": int(uptime) if isinstance(uptime, (int, float)) else None,
    }


@router.get("/index.html")
async def index_html(request: Request):
    url = app.url_path_for("internal_index")
    return RedirectResponse(url=url)


@router.get("/index", name="internal_index")
async def index(request: Request):
    counts, activity, mongo_metrics, redis_metrics = await asyncio.gather(
        _get_user_counts(),
        _get_activity(),
        _get_mongo_metrics(),
        _get_redis_metrics(),
    )
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "MomCare — Internal",
            "app_title": app.title,
            "app_version": app.version,
            "metrics": {
                "total_users": counts["total"],
                "active_users": counts["active"],
                "verified_users": counts["verified"],
                "redis_keys": redis_metrics["keys"],
            },
            "mongo_metrics": mongo_metrics,
            "redis_metrics": redis_metrics,
            "activity": activity,
            "last_updated": arrow.utcnow().to("local").format("YYYY-MM-DD HH:mm"),
        },
    )


@router.get("/api.html", name="api_health")
async def api_health(request: Request):
    mongo_metrics, redis_metrics = await asyncio.gather(
        _get_mongo_metrics(),
        _get_redis_metrics(),
    )
    api_status = "Operational" if mongo_metrics["ok"] and redis_metrics["ok"] else "Degraded"
    return templates.TemplateResponse(
        "api_health.html",
        context={
            "request": request,
            "title": "MomCare — API Health",
            "app_title": app.title,
            "app_version": app.version,
            "api_status": api_status,
            "mongo_metrics": mongo_metrics,
            "redis_metrics": redis_metrics,
            "last_updated": arrow.utcnow().to("local").format("YYYY-MM-DD HH:mm"),
        },
    )


@router.get("/users.html", name="users_health")
async def users_health(request: Request):
    counts, providers, users = await asyncio.gather(
        _get_user_counts(),
        _get_provider_counts(),
        _get_recent_users(),
    )
    provider_labels = list(providers.keys())
    provider_counts = [providers[label] for label in provider_labels]
    return templates.TemplateResponse(
        "users.html",
        context={
            "request": request,
            "title": "MomCare — Users",
            "app_title": app.title,
            "app_version": app.version,
            "metrics": counts,
            "users": users,
            "provider_labels": provider_labels,
            "provider_counts": provider_counts,
            "last_updated": arrow.utcnow().to("local").format("YYYY-MM-DD HH:mm"),
        },
    )


@router.get("/logs.html", name="logs_page")
async def logs_page(request: Request):
    return templates.TemplateResponse(
        "logs.html",
        context={
            "request": request,
            "title": "MomCare — Logs",
            "app_title": app.title,
            "app_version": app.version,
        },
    )
