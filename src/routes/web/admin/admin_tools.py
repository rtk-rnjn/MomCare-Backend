from __future__ import annotations

import asyncio
import datetime
import os
import shlex
import subprocess
import sys
import uuid
from typing import Any

import arrow
import orjson
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.database import AsyncDatabase as Database
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from redis.asyncio import Redis

from src.app import app
from src.utils.async_code_executor import Scope
from src.utils.python_repl_executor import PythonReplExecutor
from src.utils.redis_cli_executor import RedisCliExecutor
from src.utils.terminal_executor import TerminalExecutor

router = APIRouter()

database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client
mongo_client: AsyncMongoClient = app.state.mongo_client
templates: Jinja2Templates = app.state.templates

python_repl_executor = PythonReplExecutor()
redis_cli_executor = RedisCliExecutor(redis_client)
terminal_executor = TerminalExecutor()

RESTART_ENABLED = os.getenv("ADMIN_ENABLE_RESTART", "false").strip().lower() in {"1", "true", "yes", "on"}
RESTART_MODE = os.getenv("ADMIN_RESTART_MODE", "execv").strip().lower()
RESTART_DOCKER_COMMAND = os.getenv("ADMIN_RESTART_DOCKER_COMMAND", "docker restart momcare-backend").strip()
RESTART_PM2_COMMAND = os.getenv("ADMIN_RESTART_PM2_COMMAND", "pm2 restart all").strip()


def _is_docker_runtime() -> bool:
    if os.path.exists("/.dockerenv"):
        return True

    cgroup_path = "/proc/1/cgroup"
    if os.path.exists(cgroup_path):
        try:
            with open(cgroup_path, "r", encoding="utf-8") as file:
                cgroup_text = file.read().lower()
            if any(marker in cgroup_text for marker in ("docker", "containerd", "kubepods")):
                return True
        except OSError:
            pass

    return False


def _is_pm2_runtime() -> bool:
    return any(
        os.getenv(key)
        for key in (
            "pm_id",
            "PM2_HOME",
            "pm_exec_path",
            "NODE_APP_INSTANCE",
            "name",
        )
    )


def _detect_runtime_mode() -> tuple[str, str]:
    if _is_docker_runtime():
        return "docker", "Detected container runtime markers"

    if _is_pm2_runtime():
        return "pm2", "Detected PM2 environment variables"

    return "normal", "No Docker/PM2 markers detected"


def _require_input(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{key} is required")
    return value.strip()


def _build_repl_scope() -> Scope:
    return Scope(
        {
            "app": app,
            "request_app_state": app.state,
            "database": database,
            "redis_client": redis_client,
            "mongo_client": mongo_client,
            "arrow": arrow,
            "orjson": orjson,
            "datetime": datetime,
            "uuid": uuid,
            "asyncio": asyncio,
        }
    )


@router.get("/tools", include_in_schema=False)
async def admin_tools(request: Request):
    runtime_mode, runtime_reason = _detect_runtime_mode()

    return templates.TemplateResponse(
        "admin_tools.html.jinja",
        {
            "request": request,
            "allowed_redis_commands": redis_cli_executor.get_allowed_commands(),
            "restart_enabled": RESTART_ENABLED,
            "restart_mode": RESTART_MODE,
            "restart_docker_command": RESTART_DOCKER_COMMAND,
            "restart_pm2_command": RESTART_PM2_COMMAND,
            "runtime_mode": runtime_mode,
            "runtime_reason": runtime_reason,
        },
    )


async def _delayed_restart(mode: str):
    await asyncio.sleep(0.6)

    if mode == "exit":
        os._exit(0)

    if mode == "docker":
        if not RESTART_DOCKER_COMMAND:
            return

        try:
            subprocess.Popen(shlex.split(RESTART_DOCKER_COMMAND), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return
        return

    if mode == "pm2":
        if not RESTART_PM2_COMMAND:
            return

        try:
            subprocess.Popen(shlex.split(RESTART_PM2_COMMAND), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            return
        return

    try:
        os.execv(sys.executable, [sys.executable, *sys.argv])
    except Exception:
        os._exit(0)


@router.post("/tools/api/python", include_in_schema=False)
async def admin_tools_python(payload: dict[str, Any] = Body(...)):
    code = _require_input(payload, "code")
    scope = _build_repl_scope()
    result = await python_repl_executor.execute(code, scope=scope)
    return JSONResponse(result)


@router.post("/tools/api/redis", include_in_schema=False)
async def admin_tools_redis(payload: dict[str, Any] = Body(...)):
    command = _require_input(payload, "command")
    result = await redis_cli_executor.execute_command(command)
    return JSONResponse(result)


@router.post("/tools/api/terminal", include_in_schema=False)
async def admin_tools_terminal(payload: dict[str, Any] = Body(...)):
    command = _require_input(payload, "command")

    events: list[dict[str, Any]] = []
    success = True
    exit_code: int | None = None

    async for event in terminal_executor.execute_command_stream(command):
        events.append(
            {
                "type": event.get("type"),
                "data": event.get("data"),
                "exit_code": event.get("exit_code"),
            }
        )

        if event.get("type") == "error":
            success = False

        if event.get("type") == "end":
            exit_code = event.get("exit_code")
            if exit_code not in (None, 0):
                success = False

    return JSONResponse(
        {
            "success": success,
            "command": command,
            "exit_code": exit_code,
            "events": events,
        }
    )


@router.post("/tools/api/restart", include_in_schema=False)
async def admin_tools_restart(payload: dict[str, Any] = Body(...)):
    if not RESTART_ENABLED:
        raise HTTPException(status_code=403, detail="Restart is disabled. Set ADMIN_ENABLE_RESTART=true to enable it.")

    confirm = payload.get("confirm")
    if confirm is not True:
        raise HTTPException(status_code=400, detail="confirm=true is required")

    mode = payload.get("mode")
    if not isinstance(mode, str) or not mode.strip():
        mode = RESTART_MODE

    mode = mode.strip().lower()
    if mode not in {"execv", "exit", "docker", "pm2"}:
        raise HTTPException(status_code=400, detail="mode must be one of: execv, exit, docker, pm2")

    if mode == "docker" and not RESTART_DOCKER_COMMAND:
        raise HTTPException(status_code=400, detail="Docker restart is not configured. Set ADMIN_RESTART_DOCKER_COMMAND.")

    if mode == "pm2" and not RESTART_PM2_COMMAND:
        raise HTTPException(status_code=400, detail="PM2 restart is not configured. Set ADMIN_RESTART_PM2_COMMAND.")

    asyncio.create_task(_delayed_restart(mode))
    return JSONResponse({"success": True, "message": f"Restart scheduled (mode={mode})"})
