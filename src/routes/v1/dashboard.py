from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/dashboard", tags=["System & Meta"])


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    """
    API monitoring dashboard showing request statistics and system health.
    
    Displays real-time metrics including request counts, response times,
    error rates, and endpoint usage statistics.
    """
    stats = {}
    if hasattr(request.app.state, "monitoring_handler"):
        monitoring = request.app.state.monitoring_handler
        stats = monitoring.get_stats(hours=24)
    
    return request.app.state.templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats}
    )
