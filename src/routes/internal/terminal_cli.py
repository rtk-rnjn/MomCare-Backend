from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/terminal", response_class=HTMLResponse, include_in_schema=False)
async def terminal_cli_interface(request: Request):
    """
    🔒 Super Secret Secured Terminal Web Interface.

    Requires password authentication to access. Provides a beautiful web-based
    terminal for executing shell commands securely with session management.
    """
    return request.app.state.templates.TemplateResponse("terminal_cli.html", {"request": request, "app": app})
