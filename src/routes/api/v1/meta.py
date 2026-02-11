from __future__ import annotations

import os
from typing import Any, TypedDict

import arrow
import orjson
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import ORJSONResponse as _ORJSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase as Database
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from pymongo.errors import PyMongoError
from redis import RedisError
from redis.asyncio import Redis

from src.app import app

load_dotenv()

database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

security = HTTPBearer()


async def admin_required(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token != os.environ["ADMIN_TOKEN"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")


router = APIRouter(prefix="/meta", tags=["System & Meta"], dependencies=[Depends(admin_required)])


class ORJSONResponse(_ORJSONResponse):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        def default(obj):
            if isinstance(obj, Timestamp):
                return obj.as_datetime().timestamp()

            if isinstance(obj, ObjectId):
                return str(obj)
            return str(obj)

        return orjson.dumps(content, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY, default=default)


# MongoDB


class MongoServerInfo(TypedDict, total=False):
    version: str
    git_version: str
    sys_info: str
    loader_flags: str
    allocator: str
    javascript_engine: str


class MongoBuildInfo(TypedDict, total=False):
    version: str
    modules: list[str]
    bits: int
    max_bson_object_size: int


class MongoStatus(TypedDict, total=False):
    uptime_seconds: int
    connections: dict[str, Any]
    mem: dict[str, Any]
    network: dict[str, Any]
    opcounters: dict[str, int]
    asserts: dict[str, int]


class MongoReplication(TypedDict, total=False):
    set: str
    my_state: int
    members: list[dict[str, Any]]


class MongoDatabases(TypedDict):
    count: int
    names: list[str]


class MongoMetadata(TypedDict, total=False):
    ok: bool
    error: str
    server: MongoServerInfo
    build: MongoBuildInfo
    status: MongoStatus
    replication: MongoReplication | None
    databases: MongoDatabases


# Redis


class RedisServerInfo(TypedDict, total=False):
    redis_version: str
    redis_mode: str
    os: str
    arch_bits: int
    process_id: int
    uptime_in_seconds: int


class RedisClientsInfo(TypedDict, total=False):
    connected_clients: int
    blocked_clients: int
    maxclients: int


class RedisMemoryInfo(TypedDict, total=False):
    used_memory: int
    used_memory_human: str
    used_memory_peak: int
    used_memory_peak_human: str
    maxmemory: int
    mem_fragmentation_ratio: float


class RedisStatsInfo(TypedDict, total=False):
    total_connections_received: int
    total_commands_processed: int
    instantaneous_ops_per_sec: int
    keyspace_hits: int
    keyspace_misses: int
    evicted_keys: int


class RedisPersistenceInfo(TypedDict, total=False):
    rdb_last_save_time: int
    aof_enabled: int


class RedisMetadata(TypedDict, total=False):
    ok: bool
    error: str
    server: RedisServerInfo
    clients: RedisClientsInfo
    memory: RedisMemoryInfo
    stats: RedisStatsInfo
    persistence: RedisPersistenceInfo
    keyspace: dict[str, Any]


@router.get("/version", summary="Get API Version", description="Retrieve the current version of the MomCare API.", response_model=str)
async def get_api_version() -> str:
    return app.version


@router.get("/status", summary="Get API Status", description="Check the health status of the MomCare API.", response_model=str)
async def get_api_status() -> str:
    return "OK"


@router.get("/uptime", summary="Get API Uptime", description="Retrieve the uptime of the MomCare API in seconds.", response_model=int)
async def get_api_uptime() -> int:
    start_time: arrow.Arrow = app.state.start_time
    now = arrow.utcnow()
    uptime_seconds = (now - start_time).total_seconds()
    return int(uptime_seconds)


database_router = APIRouter(prefix="/database", tags=["System & Meta"])


async def extract_mongo_metadata(mongo_client: AsyncMongoClient) -> MongoMetadata:
    """
    Extract operational + topology metadata from MongoDB.
    Designed for admin dashboards and health monitoring.
    """
    metadata: MongoMetadata = {}

    try:
        # Basic server info
        server_info = await mongo_client.server_info()

        metadata["server"] = MongoServerInfo(
            version=server_info.get("version"),
            git_version=server_info.get("gitVersion"),
            sys_info=server_info.get("sysInfo"),
            loader_flags=server_info.get("loaderFlags"),
            allocator=server_info.get("allocator"),
            javascript_engine=server_info.get("javascriptEngine"),
        )

        # Build info
        build_info = await mongo_client.admin.command("buildInfo")
        metadata["build"] = MongoBuildInfo(
            version=build_info.get("version"),
            modules=build_info.get("modules"),
            bits=build_info.get("bits"),
            max_bson_object_size=build_info.get("maxBsonObjectSize"),
        )

        # Server status (heavy but admin-critical)
        server_status = await mongo_client.admin.command("serverStatus")
        metadata["status"] = MongoStatus(
            uptime_seconds=server_status.get("uptime"),
            connections=server_status.get("connections"),
            mem=server_status.get("mem"),
            network=server_status.get("network"),
            opcounters=server_status.get("opcounters"),
            asserts=server_status.get("asserts"),
        )

        try:
            repl_status = await mongo_client.admin.command("replSetGetStatus")
            metadata["replication"] = MongoReplication(
                set=repl_status.get("set"),
                my_state=repl_status.get("myState"),
                members=repl_status.get("members"),
            )
        except PyMongoError:
            metadata["replication"] = None  # Not a replica set

        # Databases overview
        dbs = await mongo_client.list_database_names()
        metadata["databases"] = {
            "count": len(dbs),
            "names": dbs,
        }

        metadata["ok"] = True

    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving MongoDB metadata: {str(e)}")

    return metadata


@database_router.get(
    "/mongodb/stats",
    summary="Get Database Stats",
    description="Retrieve statistics about the MongoDB database, including collection counts and storage size.",
    response_model=dict,
)
async def get_database_stats() -> ORJSONResponse:
    mongo_client = app.state.mongo_client
    metadata = await extract_mongo_metadata(mongo_client)
    return ORJSONResponse(content=metadata)


async def extract_redis_metadata(redis_client: Redis) -> RedisMetadata:
    """
    Extract operational metadata from Redis.
    Suitable for admin dashboards and infra monitoring.
    """
    metadata: RedisMetadata = {}

    try:
        info = await redis_client.info()

        metadata["server"] = {
            "redis_version": info.get("redis_version"),
            "redis_mode": info.get("redis_mode"),
            "os": info.get("os"),
            "arch_bits": info.get("arch_bits"),
            "process_id": info.get("process_id"),
            "uptime_in_seconds": info.get("uptime_in_seconds"),
        }

        metadata["clients"] = {
            "connected_clients": info.get("connected_clients"),
            "blocked_clients": info.get("blocked_clients"),
            "maxclients": info.get("maxclients"),
        }

        metadata["memory"] = {
            "used_memory": info.get("used_memory"),
            "used_memory_human": info.get("used_memory_human"),
            "used_memory_peak": info.get("used_memory_peak"),
            "used_memory_peak_human": info.get("used_memory_peak_human"),
            "maxmemory": info.get("maxmemory"),
            "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio"),
        }

        metadata["stats"] = {
            "total_connections_received": info.get("total_connections_received"),
            "total_commands_processed": info.get("total_commands_processed"),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
            "evicted_keys": info.get("evicted_keys"),
        }

        metadata["persistence"] = {
            "rdb_last_save_time": info.get("rdb_last_save_time"),
            "aof_enabled": info.get("aof_enabled"),
        }

        metadata["keyspace"] = info.get("keyspace", {})

        metadata["ok"] = True

    except RedisError as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving Redis info: {str(e)}")

    return metadata


@database_router.get(
    "/redis/stats",
    summary="Get Redis Stats",
    description="Retrieve statistics about the Redis instance, including memory usage and uptime.",
    response_model=RedisMetadata,
)
async def get_redis_stats() -> ORJSONResponse:
    redis_client = app.state.redis_client
    metadata = await extract_redis_metadata(redis_client)
    return ORJSONResponse(content=metadata)


router.include_router(database_router)
