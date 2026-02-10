from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.app import app

templates: Jinja2Templates = app.state.templates

router = APIRouter(include_in_schema=False)


@router.get("/index.html")
async def index_html(request: Request):
    url = app.url_path_for("internal_index")
    return RedirectResponse(url=url)


@router.get("/index", name="internal_index")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "title": "MomCare — Internal",
            "app_title": app.title,
            "app_version": app.version,
        },
    )
