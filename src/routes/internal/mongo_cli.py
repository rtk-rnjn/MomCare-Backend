from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/database/mongo-cli", response_class=HTMLResponse, include_in_schema=False)
async def mongo_cli_interface(request: Request):
    """
    🔒 Super Secret Secured MongoDB CLI Web Interface.

    Requires password authentication to access. Provides a beautiful web-based
    terminal for executing MongoDB commands securely with session management.
    """
    return request.app.state.templates.TemplateResponse("mongo_cli.html", {"request": request, "app": app})
