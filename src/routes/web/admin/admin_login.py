from __future__ import annotations

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.app import app

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

templates: Jinja2Templates = app.state.templates
router = APIRouter()


@router.get("/login")
async def admin_login_get(request: Request):
    return templates.TemplateResponse("admin_login.html.jinja", {"request": request, "error": None})


@router.post("/login")
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        request.session["admin_logged_in"] = True
        dashboard_url = app.url_path_for("admin_dashboard")
        return RedirectResponse(dashboard_url, status_code=303)

    return templates.TemplateResponse(
        "admin_login.html.jinja",
        {"request": request, "error": "Invalid username or password"},
    )


@router.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.pop("admin_logged_in", None)
    login_url = app.url_path_for("admin_login_get")
    return RedirectResponse(login_url, status_code=303)
