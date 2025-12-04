from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def internal_dashboard(request: Request):
    """
    API monitoring dashboard showing request statistics and system health.

    Displays real-time metrics including request counts, response times,
    error rates, and endpoint usage statistics.
    """
    stats = {}
    if hasattr(request.app.state, "monitoring_handler"):
        monitoring = request.app.state.monitoring_handler
        stats = monitoring.get_stats(hours=24)

    return request.app.state.templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats, "app": app})
