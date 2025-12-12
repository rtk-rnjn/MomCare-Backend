from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/database/redis-cli", response_class=HTMLResponse, include_in_schema=False)
async def redis_cli_interface(request: Request):
    """
    🔒 Super Secret Secured Redis CLI Web Interface.

    Requires password authentication to access. Provides a beautiful web-based
    terminal for executing Redis commands securely with session management.
    """
    return app.state.templates.TemplateResponse("redis_cli.html", {"request": request, "app": app})
