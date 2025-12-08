from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/system", response_class=HTMLResponse, include_in_schema=False)
async def system_monitor_page(request: Request):
    """
    Real-time system monitoring dashboard with CPU, RAM usage graphs and logs.

    Shows live system metrics, process information, and PM2 data if available.
    """
    return request.app.state.templates.TemplateResponse("system_monitor.html", {"request": request, "app": app})
