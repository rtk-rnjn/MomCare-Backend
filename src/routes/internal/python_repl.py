from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/_/python-repl", response_class=HTMLResponse, include_in_schema=False)
async def python_repl_interface(request: Request):
    """
    🔒 Super Secret Secured Python REPL Web Interface.

    Requires password authentication to access. Provides a beautiful web-based
    Python REPL for executing code securely with session management and state preservation.
    """
    return request.app.state.templates.TemplateResponse("python_repl.html", {"request": request, "app": app})
