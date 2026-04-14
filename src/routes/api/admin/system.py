from __future__ import annotations

import logging
import os
import signal
import sys
import time

import arrow
import psutil
from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.asynchronous.collection import AsyncCollection
from redis.asyncio import Redis

from src.app import app
from src.utils.admin_auth import AdminAccessPayload, get_client_ip, require_admin, require_super_admin
from src.utils.audit_logger import AuditLogger

router = APIRouter(prefix="/system", tags=["Admin System"])

db = app.state.mongo_database
redis_client: Redis = app.state.redis_client
audit_collection: AsyncCollection = db["audit_logs"]
http_logs_collection: AsyncCollection = db["http_logs"]
audit_logger = AuditLogger(audit_collection)

logger = logging.getLogger(__name__)

ADMIN_ENABLE_RESTART = os.getenv("ADMIN_ENABLE_RESTART", "false").lower() == "true"


@router.get("/dashboard")
async def dashboard_overview(admin: AdminAccessPayload = Depends(require_admin)):
    start_time: arrow.Arrow = app.state.start_time
    uptime_seconds = (arrow.utcnow() - start_time).total_seconds()

    # System metrics
    process = psutil.Process()
    memory = process.memory_info()

    # DB connectivity
    try:
        await redis_client.ping()
        redis_connected = True
    except Exception:
        redis_connected = False

    try:
        await db.command("ping")
        mongo_connected = True
    except Exception:
        mongo_connected = False

    # Request volume from logs
    total_requests = await http_logs_collection.estimated_document_count()

    now = time.time()
    last_hour_errors = await http_logs_collection.count_documents({"status_code": {"$gte": 400}, "timestamp": {"$gte": now - 3600}})
    last_hour_total = await http_logs_collection.count_documents({"timestamp": {"$gte": now - 3600}})
    error_rate = (last_hour_errors / last_hour_total * 100) if last_hour_total > 0 else 0

    # User counts
    users_collection: AsyncCollection = db["users"]
    credentials_collection: AsyncCollection = db["credentials"]
    total_users = await users_collection.estimated_document_count()
    active_users = await credentials_collection.count_documents({"account_status": "ACTIVE"})
    locked_users = await credentials_collection.count_documents({"account_status": "LOCKED"})

    return {
        "version": app.version,
        "uptime_seconds": round(uptime_seconds, 2),
        "start_time": start_time.isoformat(),
        "system": {
            "cpu_percent": process.cpu_percent(),
            "memory_rss_mb": round(memory.rss / (1024 * 1024), 2),
            "memory_vms_mb": round(memory.vms / (1024 * 1024), 2),
            "pid": process.pid,
            "python_version": sys.version,
        },
        "database": {
            "redis_connected": redis_connected,
            "mongo_connected": mongo_connected,
        },
        "requests": {
            "total": total_requests,
            "last_hour_total": last_hour_total,
            "last_hour_errors": last_hour_errors,
            "error_rate_percent": round(error_rate, 2),
        },
        "users": {
            "total": total_users,
            "active": active_users,
            "locked": locked_users,
        },
        "restart_enabled": ADMIN_ENABLE_RESTART,
    }


@router.post("/restart")
async def restart_server(request: Request, admin: AdminAccessPayload = Depends(require_super_admin)):
    if not ADMIN_ENABLE_RESTART:
        raise HTTPException(status_code=403, detail="Server restart is disabled by ADMIN_ENABLE_RESTART feature flag")

    await audit_logger.log(
        admin_id=admin["sub"],
        admin_username=admin["username"],
        action="server_restart",
        target_type="system",
        metadata={"reason": "Admin-initiated restart"},
        ip_address=get_client_ip(request),
    )

    logger.warning(f"Server restart initiated by admin {admin['username']} ({admin['sub']})")

    # Send SIGHUP to gracefully restart (works with process managers like systemd/supervisor)
    os.kill(os.getpid(), signal.SIGHUP)

    return {"detail": "Server restart initiated"}


@router.get("/health")
async def health_check(admin: AdminAccessPayload = Depends(require_admin)):
    checks = {}

    try:
        await redis_client.ping()
        checks["redis"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}

    try:
        start = time.time()
        await db.command("ping")
        latency = (time.time() - start) * 1000
        checks["mongodb"] = {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        checks["mongodb"] = {"status": "unhealthy", "error": str(e)}

    overall = "healthy" if all(c["status"] == "healthy" for c in checks.values()) else "degraded"

    return {"status": overall, "checks": checks}
