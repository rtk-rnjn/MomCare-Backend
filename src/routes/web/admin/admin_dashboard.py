from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from src.app import app

templates: Jinja2Templates = app.state.templates

router = APIRouter()


@router.get("/dashboard", include_in_schema=False)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("base.html.jinja", {"request": request})
