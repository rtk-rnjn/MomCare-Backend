from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from src.app import app


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/home", response_class=HTMLResponse, include_in_schema=False)
@app.get("/index", response_class=HTMLResponse, include_in_schema=False)
async def index_page(request: Request) -> HTMLResponse:
    """
    Home page of the MomCare application.

    Serves the main landing page with information about the application.
    """
    return request.app.state.templates.TemplateResponse("index.html", {"request": request, "app": app})
