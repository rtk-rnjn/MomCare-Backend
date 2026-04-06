from __future__ import annotations

import uuid

import arrow
import bcrypt
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models.admin import AdminLoginAttemptDict, AdminUserDict, make_login_attempt
from src.utils.admin_auth import check_ip_allowlist, check_login_rate_limit, generate_csrf_token, get_client_ip

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

admin_users: Collection[AdminUserDict] = database["admin_users"]
admin_login_attempts: Collection[AdminLoginAttemptDict] = database["admin_login_attempts"]

router = APIRouter()


@router.get("/login", name="admin_login_get")
async def admin_login_get(request: Request):
    if request.session.get("admin_logged_in"):
        return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
    return templates.TemplateResponse("admin_login.html.jinja", {"request": request, "error": None})


@router.post("/login", name="admin_login_post")
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    check_ip_allowlist(request)
    await check_login_rate_limit(request)

    ip_addr = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    admin = await admin_users.find_one({"username": username, "is_active": True})

    if admin is None or not bcrypt.checkpw(password.encode(), admin["password_hash"].encode()):
        attempt = make_login_attempt(
            username=username,
            ip_address=ip_addr,
            success=False,
            user_agent=user_agent,
            failure_reason="Invalid credentials" if admin is None else "Wrong password",
        )
        await admin_login_attempts.insert_one(attempt)
        return templates.TemplateResponse(
            "admin_login.html.jinja",
            {"request": request, "error": "Invalid username or password."},
            status_code=401,
        )

    attempt = make_login_attempt(username=username, ip_address=ip_addr, success=True, user_agent=user_agent)
    await admin_login_attempts.insert_one(attempt)

    await admin_users.update_one({"_id": admin["_id"]}, {"$set": {"last_login_timestamp": arrow.utcnow().timestamp()}})

    session_id = str(uuid.uuid4())
    request.session["admin_logged_in"] = True
    request.session["admin_id"] = admin["_id"]
    request.session["admin_username"] = admin["username"]
    request.session["admin_display_name"] = admin.get("display_name", admin["username"])
    request.session["admin_role"] = admin.get("role", "operator")
    request.session["admin_session_id"] = session_id

    csrf_token = generate_csrf_token(session_id)
    response = RedirectResponse(url=request.url_for("admin_dashboard"), status_code=303)
    response.set_cookie("csrf_token", csrf_token, httponly=False, samesite="strict", max_age=3600)
    return response


@router.get("/logout", name="admin_logout")
async def admin_logout(request: Request):
    request.session.clear()
    response = RedirectResponse(url=request.url_for("admin_login_get"), status_code=303)
    response.delete_cookie("csrf_token")
    return response
