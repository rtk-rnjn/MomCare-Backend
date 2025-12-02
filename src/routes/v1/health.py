from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/health", tags=["System & Meta"])


@router.get("/database", response_class=HTMLResponse, include_in_schema=False)
async def database_health_page(request: Request):
    """
    Database health monitoring dashboard showing MongoDB and Redis statistics.

    Displays real-time health metrics including connection status, storage usage,
    document counts, memory usage, and performance statistics.
    """
    stats = {}
    if hasattr(request.app.state, "database_monitor"):
        monitor = request.app.state.database_monitor
        stats = await monitor.get_all_stats()

    return request.app.state.templates.TemplateResponse("database_health.html", {"request": request, "stats": stats})


@router.get("/database/json", response_class=JSONResponse)
async def database_health_json(request: Request):
    """
    Get database health statistics in JSON format.

    Returns detailed health metrics for MongoDB and Redis including
    version info, uptime, connections, storage, and performance stats.
    """
    if hasattr(request.app.state, "database_monitor"):
        monitor = request.app.state.database_monitor
        return await monitor.get_all_stats()

    return {"error": "Database monitor not available"}
