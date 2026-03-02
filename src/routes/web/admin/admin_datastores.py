from __future__ import annotations

import inspect
from typing import Any

import orjson
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis

from src.app import app

router = APIRouter()

database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
templates: Jinja2Templates = app.state.templates

MAX_REDIS_SCAN_COUNT = 200
MAX_REDIS_VALUE_ITEMS = 200
MAX_MONGO_PAGE_SIZE = 100


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _jsonable(value: Any) -> Any:
    return orjson.loads(orjson.dumps(value, default=str))


def _safe_filter(raw: str | None) -> dict:
    if not raw:
        return {}

    try:
        parsed = orjson.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid filter JSON")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Filter must be a JSON object")

    return parsed


def _validate_page_params(page: int, page_size: int, max_page_size: int) -> tuple[int, int]:
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), max_page_size))
    return page, page_size


async def _summarize_redis_keys(keys: list[str]) -> list[dict[str, Any]]:
    if not keys:
        return []

    pipe = redis_client.pipeline()
    for key in keys:
        pipe.type(key)
        pipe.ttl(key)
    type_ttl_results = await pipe.execute()

    typed_keys: list[tuple[str, int]] = []
    for idx in range(0, len(type_ttl_results), 2):
        key_type = _decode(type_ttl_results[idx])
        ttl = type_ttl_results[idx + 1]
        typed_keys.append((str(key_type), int(ttl if ttl is not None else -1)))

    length_pipe = redis_client.pipeline()
    for key, (key_type, _) in zip(keys, typed_keys):
        if key_type == "string":
            length_pipe.strlen(key)
        elif key_type == "hash":
            length_pipe.hlen(key)
        elif key_type == "list":
            length_pipe.llen(key)
        elif key_type == "set":
            length_pipe.scard(key)
        elif key_type == "zset":
            length_pipe.zcard(key)
        else:
            length_pipe.get(key)

    length_results = await length_pipe.execute()

    summarized: list[dict[str, Any]] = []
    for key, (key_type, ttl), length in zip(keys, typed_keys, length_results):
        summarized.append(
            {
                "key": _decode(key),
                "type": key_type,
                "ttl": int(ttl),
                "approx_length": int(length) if isinstance(length, (int, float)) else None,
            }
        )

    return summarized


async def _read_redis_value(key: str, key_type: str, max_items: int) -> Any:
    if key_type == "string":
        value = await redis_client.get(key)
        return _decode(value)

    if key_type == "hash":
        raw = redis_client.hgetall(key)
        if inspect.isawaitable(raw):
            raw = await raw

        return {str(_decode(k)): _decode(v) for k, v in raw.items()}

    if key_type == "list":
        raw = redis_client.lrange(key, 0, max_items - 1)
        if inspect.isawaitable(raw):
            raw = await raw

        return [_decode(item) for item in raw]

    if key_type == "set":
        raw = redis_client.smembers(key)
        if inspect.isawaitable(raw):
            raw = await raw

        return sorted(_decode(item) for item in raw)

    if key_type == "zset":
        raw = await redis_client.zrange(key, 0, max_items - 1, withscores=True)
        return [{"member": _decode(member), "score": score} for member, score in raw]

    return None


async def _get_collection(collection_name: str) -> Collection:
    try:
        names = await database.list_collection_names()
    except Exception:
        raise HTTPException(status_code=500, detail="Unable to list collections")

    if collection_name not in names:
        raise HTTPException(status_code=404, detail="Collection not found")

    return database[collection_name]


@router.get("/datastores", include_in_schema=False, name="admin_datastores")
async def admin_datastores(request: Request):
    redis_info: dict[str, Any] = {"available": False, "dbsize": 0, "connected_clients": 0, "used_memory_human": "-"}
    try:
        maybe_awaitable = redis_client.ping()
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable
        info = await redis_client.info()
        redis_info = {
            "available": True,
            "dbsize": await redis_client.dbsize(),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "-"),
        }
    except Exception:
        pass

    try:
        mongo_collections = sorted(await database.list_collection_names())
    except Exception:
        mongo_collections = []

    return templates.TemplateResponse(
        "datastores.html.jinja",
        {
            "request": request,
            "redis_info": redis_info,
            "mongo_collections": mongo_collections,
        },
    )


@router.get("/datastores/api/redis/scan", include_in_schema=False)
async def admin_datastores_redis_scan(
    pattern: str = Query("*"),
    count: int = Query(50, ge=1, le=MAX_REDIS_SCAN_COUNT),
    cursor: int = Query(0, ge=0),
):
    pattern = pattern.strip() or "*"
    cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=count)
    key_details = await _summarize_redis_keys(keys)
    return JSONResponse({"cursor": cursor, "keys": key_details, "has_more": cursor != 0})


@router.get("/datastores/api/redis/key/{key_path:path}", include_in_schema=False)
async def admin_datastores_redis_key_detail(key_path: str, max_items: int = Query(50, ge=1, le=MAX_REDIS_VALUE_ITEMS)):
    key = key_path
    key_type_raw = await redis_client.type(key)
    key_type = _decode(key_type_raw)
    ttl = await redis_client.ttl(key)

    value = await _read_redis_value(key, key_type, max_items=max_items)
    return JSONResponse({"key": key, "type": key_type, "ttl": ttl, "value": _jsonable(value)})


@router.post("/datastores/api/redis/key/{key_path:path}", include_in_schema=False)
async def admin_datastores_redis_upsert(key_path: str, payload: dict[str, Any] = Body(...)):
    key = key_path
    value = payload.get("value")
    ttl = payload.get("ttl")

    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="value must be a string")

    await redis_client.set(key, value)
    if isinstance(ttl, (int, float)) and int(ttl) > 0:
        await redis_client.expire(key, int(ttl))

    return JSONResponse({"ok": True})


@router.delete("/datastores/api/redis/key/{key_path:path}", include_in_schema=False)
async def admin_datastores_redis_delete(key_path: str):
    key = key_path
    deleted = await redis_client.delete(key)
    return JSONResponse({"deleted": deleted})


@router.post("/datastores/api/redis/key/{key_path:path}/expire", include_in_schema=False)
async def admin_datastores_redis_expire(key_path: str, payload: dict[str, Any] = Body(...)):
    key = key_path
    ttl = payload.get("ttl")
    if not isinstance(ttl, (int, float)):
        raise HTTPException(status_code=400, detail="ttl must be a number")

    ttl = int(ttl)
    if ttl <= 0:
        await redis_client.persist(key)
        return JSONResponse({"ok": True, "ttl": -1})

    await redis_client.expire(key, ttl)
    return JSONResponse({"ok": True, "ttl": ttl})


@router.get("/datastores/api/mongo/collections", include_in_schema=False)
async def admin_datastores_mongo_collections(include_counts: bool = Query(True)):
    names = sorted(await database.list_collection_names())

    collections: list[dict[str, Any]] = []
    if include_counts:
        for name in names:
            try:
                collection = database[name]
                count = await collection.estimated_document_count()
            except Exception:
                count = None
            collections.append({"name": name, "count": count})
    else:
        collections = [{"name": name, "count": None} for name in names]

    return JSONResponse({"collections": collections})


@router.get("/datastores/api/mongo/collection/{collection_name}", include_in_schema=False)
async def admin_datastores_mongo_collection_documents(
    collection_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_MONGO_PAGE_SIZE),
    filter: str | None = Query(None, alias="filter"),
    sort_field: str = Query("_id"),
    sort_dir: int = Query(-1),
):
    collection = await _get_collection(collection_name)
    page, page_size = _validate_page_params(page, page_size, MAX_MONGO_PAGE_SIZE)

    filter_doc = _safe_filter(filter)
    sort_dir = 1 if sort_dir >= 0 else -1

    total = await collection.count_documents(filter_doc)
    cursor = collection.find(filter_doc)
    if sort_field:
        cursor = cursor.sort(sort_field, sort_dir)

    cursor = cursor.skip((page - 1) * page_size).limit(page_size)
    docs = await cursor.to_list(length=page_size)

    return JSONResponse(
        {
            "items": [_jsonable(doc) for doc in docs],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    )


@router.get("/datastores/api/mongo/collection/{collection_name}/stats", include_in_schema=False)
async def admin_datastores_mongo_collection_stats(collection_name: str):
    collection = await _get_collection(collection_name)
    try:
        stats = await database.command({"collstats": collection.name})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch stats: {exc}")

    wanted_keys = (
        "ns",
        "count",
        "size",
        "avgObjSize",
        "storageSize",
        "nindexes",
        "totalIndexSize",
        "wiredTiger",
    )
    slim_stats = {key: stats[key] for key in wanted_keys if key in stats}
    return JSONResponse({"collection": collection.name, "stats": _jsonable(slim_stats)})
