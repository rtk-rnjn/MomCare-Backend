from __future__ import annotations

import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.utils.redis_cli_executor import RedisCliExecutor

load_dotenv()

router = APIRouter(prefix="/health", tags=["System & Meta"])


class RedisCommand(BaseModel):
    command: str


class AuthRequest(BaseModel):
    password: str

_active_tokens: dict[str, float] = {}

REDIS_CLI_PASSWORD = os.environ["REDIS_CLI_PASSWORD"]
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


def _cleanup_expired_tokens():
    """Remove expired tokens."""
    current_time = time.time()
    expired = [token for token, expiry in _active_tokens.items() if expiry < current_time]
    for token in expired:
        del _active_tokens[token]


def _verify_token(token: str | None) -> bool:
    """Verify if token is valid and not expired."""
    if not token:
        return False
    _cleanup_expired_tokens()
    return token in _active_tokens


@router.get("/database", response_class=HTMLResponse, include_in_schema=False)
async def database_health_page(request: Request):
    """
    Database health monitoring dashboard showing MongoDB and Redis statistics.

    Displays real-time health metrics including connection status, storage usage,
    document counts, memory usage, and performance statistics.
    """
    stats = {}
    if hasattr(request.app.state, "database_monitor"):
        monitor = request.app.state.database_monitor
        stats = await monitor.get_all_stats()

    return request.app.state.templates.TemplateResponse("database_health.html", {"request": request, "stats": stats})


@router.get("/database/json", response_class=JSONResponse)
async def database_health_json(request: Request):
    """
    Get database health statistics in JSON format.

    Returns detailed health metrics for MongoDB and Redis including
    version info, uptime, connections, storage, and performance stats.
    """
    if hasattr(request.app.state, "database_monitor"):
        monitor = request.app.state.database_monitor
        return await monitor.get_all_stats()

    return {"error": "Database monitor not available"}


@router.get("/database/redis-cli", response_class=HTMLResponse, include_in_schema=False)
async def redis_cli_interface(request: Request):
    """
    🔒 Super Secret Secured Redis CLI Web Interface.

    Requires password authentication to access. Provides a beautiful web-based
    terminal for executing Redis commands securely with session management.
    """
    return request.app.state.templates.TemplateResponse("redis_cli.html", {"request": request})


@router.post("/database/redis-cli/authenticate", response_class=JSONResponse)
async def authenticate_redis_cli(auth: AuthRequest):
    """
    Authenticate to access Redis CLI.

    Validates the secret password and returns a session token for subsequent requests.
    """
    if not RedisCliExecutor.verify_password(auth.password, RedisCliExecutor.hash_password(REDIS_CLI_PASSWORD)):
        return JSONResponse(content={"success": False, "error": "Invalid password"}, status_code=401)

    token = secrets.token_urlsafe(32)
    _active_tokens[token] = time.time() + TOKEN_EXPIRY_SECONDS

    return JSONResponse(content={"success": True, "token": token, "expires_in": TOKEN_EXPIRY_SECONDS})


@router.get("/database/redis-cli/verify", response_class=JSONResponse)
async def verify_redis_cli_session(x_redis_cli_token: str | None = Header(None)):
    """
    Verify if the current session token is valid.

    Used to check authentication status without requiring password re-entry.
    """
    if not _verify_token(x_redis_cli_token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return JSONResponse(content={"success": True})


@router.post("/database/redis-cli/execute", response_class=JSONResponse)
async def execute_redis_command(request: Request, command: RedisCommand, x_redis_cli_token: str | None = Header(None)):
    """
    Execute a Redis command securely.

    Requires valid authentication token. Only whitelisted commands are allowed.
    Dangerous commands like FLUSHDB, FLUSHALL, and CONFIG are blocked.
    """
    if not _verify_token(x_redis_cli_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if not hasattr(request.app.state, "database_monitor"):
        raise HTTPException(status_code=503, detail="Database monitor not available")

    monitor = request.app.state.database_monitor
    executor = RedisCliExecutor(monitor.redis_client)

    result = await executor.execute_command(command.command)
    return JSONResponse(content=result)


@router.get("/database/redis-cli/allowed-commands", response_class=JSONResponse)
async def get_allowed_redis_commands(request: Request, x_redis_cli_token: str | None = Header(None)):
    """
    Get list of allowed Redis commands.

    Requires authentication. Returns the whitelist of Redis commands that can
    be executed through the web interface.
    """
    if not _verify_token(x_redis_cli_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if not hasattr(request.app.state, "database_monitor"):
        raise HTTPException(status_code=503, detail="Database monitor not available")

    monitor = request.app.state.database_monitor
    executor = RedisCliExecutor(monitor.redis_client)

    return JSONResponse(content=executor.get_allowed_commands())
