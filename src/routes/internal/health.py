from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/database", response_class=HTMLResponse, include_in_schema=False)
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

    return request.app.state.templates.TemplateResponse("database_health.html", {"request": request, "stats": stats, "app": app})
