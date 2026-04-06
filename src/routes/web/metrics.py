from __future__ import annotations

import psutil
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from src.app import app
from src.utils.metrics import collect_runtime_metrics

redis_client: Redis = app.state.redis_client

metrics_router = APIRouter(tags=["System & Meta"])


@metrics_router.get("/metrics", summary="Operational Metrics", description="Expose operational metrics for monitoring.")
async def get_metrics(duration_sec: int = Query(300, ge=60, le=3600)):
    runtime = await collect_runtime_metrics(redis_client, duration_sec)

    virtual_memory = psutil.virtual_memory()
    disk_usage = psutil.disk_usage("/")

    system = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_percent": virtual_memory.percent,
        "ram_used_bytes": virtual_memory.used,
        "ram_total_bytes": virtual_memory.total,
        "disk_percent": disk_usage.percent,
        "disk_used_bytes": disk_usage.used,
        "disk_total_bytes": disk_usage.total,
    }

    return JSONResponse({
        "system": system,
        "requests": {
            "total": runtime["total_requests"],
            "per_second": runtime["requests_per_second"],
            "current_second_rps": runtime["current_second_rps"],
        },
        "errors": {
            "total_4xx": runtime["total_404"],
            "total_500": runtime["total_500"],
            "total_5xx": runtime["total_5xx"],
        },
        "endpoint_traffic": runtime["endpoint_traffic"],
        "endpoint_failures": runtime["endpoint_failures"],
        "duration_sec": runtime["duration_sec"],
    })
