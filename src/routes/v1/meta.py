from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.app import app

router = APIRouter()


@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root(request: Request):
    """
    Root endpoint redirecting to API documentation.

    Automatically redirects users to the Swagger UI documentation
    for easy access to API exploration and testing.
    """
    if app.docs_url:
        return RedirectResponse(url=app.docs_url)


@app.get("/_/index", response_class=HTMLResponse, include_in_schema=False)
async def internal_index_page(request: Request):
    """
    Internal team dashboard index page with links to all monitoring tools.

    Central hub for accessing API monitoring, database health, Redis CLI,
    and documentation interfaces for the development team.
    """
    return request.app.state.templates.TemplateResponse("index.html", {"request": request, "version": app.version})
