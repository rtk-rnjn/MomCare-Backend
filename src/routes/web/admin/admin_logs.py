from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from src.app import app

router = APIRouter()
templates: Jinja2Templates = app.state.templates


@router.get("/logs", include_in_schema=False)
async def admin_logs(request: Request):
    return templates.TemplateResponse("logs.html.jinja", {"request": request})
