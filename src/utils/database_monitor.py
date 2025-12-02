from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis


class DatabaseMonitor:
    def __init__(self, mongo_client: AsyncIOMotorClient, redis_client: Redis):
        self.mongo_client = mongo_client
        self.redis_client = redis_client

    async def get_mongodb_stats(self) -> dict[str, Any]:
        """Get MongoDB statistics and health information."""
        try:
            # Server status
            server_status = await self.mongo_client.admin.command("serverStatus")

            # Database stats
            db = self.mongo_client["MomCare"]
            db_stats = await db.command("dbStats")

            # Collection counts
            collections = await db.list_collection_names()
            collection_stats = {}

            for collection_name in collections:
                count = await db[collection_name].count_documents({})
                collection_stats[collection_name] = count

            return {
                "status": "healthy",
                "version": server_status.get("version", "unknown"),
                "uptime_seconds": server_status.get("uptime", 0),
                "connections": {
                    "current": server_status.get("connections", {}).get("current", 0),
                    "available": server_status.get("connections", {}).get("available", 0),
                },
                "network": {
                    "bytes_in": server_status.get("network", {}).get("bytesIn", 0),
                    "bytes_out": server_status.get("network", {}).get("bytesOut", 0),
                    "requests": server_status.get("network", {}).get("numRequests", 0),
                },
                "storage": {
                    "data_size_mb": round(db_stats.get("dataSize", 0) / (1024 * 1024), 2),
                    "storage_size_mb": round(db_stats.get("storageSize", 0) / (1024 * 1024), 2),
                    "index_size_mb": round(db_stats.get("indexSize", 0) / (1024 * 1024), 2),
                    "total_collections": db_stats.get("collections", 0),
                    "total_indexes": db_stats.get("indexes", 0),
                },
                "collections": collection_stats,
                "operations": {
                    "insert": server_status.get("opcounters", {}).get("insert", 0),
                    "query": server_status.get("opcounters", {}).get("query", 0),
                    "update": server_status.get("opcounters", {}).get("update", 0),
                    "delete": server_status.get("opcounters", {}).get("delete", 0),
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    async def get_redis_stats(self) -> dict[str, Any]:
        """Get Redis statistics and health information."""
        try:
            info = await self.redis_client.info()

            # Get key count for the specific database
            db_info = await self.redis_client.info("keyspace")
            db_key = f"db{self.redis_client.connection_pool.connection_kwargs.get('db', 0)}"
            db_stats = db_info.get(db_key, {})

            return {
                "status": "healthy",
                "version": info.get("redis_version", "unknown"),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
                "connected_clients": info.get("connected_clients", 0),
                "memory": {
                    "used_memory_mb": round(info.get("used_memory", 0) / (1024 * 1024), 2),
                    "used_memory_peak_mb": round(info.get("used_memory_peak", 0) / (1024 * 1024), 2),
                    "used_memory_rss_mb": round(info.get("used_memory_rss", 0) / (1024 * 1024), 2),
                    "maxmemory_mb": (
                        round(info.get("maxmemory", 0) / (1024 * 1024), 2) if info.get("maxmemory", 0) > 0 else "unlimited"
                    ),
                },
                "stats": {
                    "total_connections_received": info.get("total_connections_received", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "hit_rate": (
                        round(
                            (info.get("keyspace_hits", 0) / (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1))) * 100, 2
                        )
                        if (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0)) > 0
                        else 0
                    ),
                },
                "keys": {
                    "total_keys": db_stats.get("keys", 0) if isinstance(db_stats, dict) else 0,
                    "expires": db_stats.get("expires", 0) if isinstance(db_stats, dict) else 0,
                },
                "persistence": {
                    "rdb_last_save_time": info.get("rdb_last_save_time", 0),
                    "rdb_changes_since_last_save": info.get("rdb_changes_since_last_save", 0),
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }

    async def get_all_stats(self) -> dict[str, Any]:
        """Get all database statistics."""
        mongo_stats = await self.get_mongodb_stats()
        redis_stats = await self.get_redis_stats()

        return {
            "mongodb": mongo_stats,
            "redis": redis_stats,
            "overall_status": (
                "healthy" if mongo_stats.get("status") == "healthy" and redis_stats.get("status") == "healthy" else "degraded"
            ),
        }
