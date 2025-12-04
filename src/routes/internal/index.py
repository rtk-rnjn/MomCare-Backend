from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/index", response_class=HTMLResponse, include_in_schema=False)
async def internal_index_page(request: Request):
    """
    Internal team dashboard index page with links to all monitoring tools.

    Central hub for accessing API monitoring, database health, Redis CLI,
    and documentation interfaces for the development team.
    """
    return request.app.state.templates.TemplateResponse("index.html", {"request": request, "version": app.version, "app": app})
