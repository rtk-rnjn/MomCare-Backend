from __future__ import annotations

import asyncio
import json
import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.utils.mongo_cli_executor import MongoCliExecutor
from src.utils.python_repl_executor import PythonReplExecutor
from src.utils.redis_cli_executor import RedisCliExecutor
from src.utils.terminal_executor import TerminalExecutor

load_dotenv()

router = APIRouter(prefix="/health", tags=["System & Meta"], include_in_schema=False)


class Command(BaseModel):
    command: str


class AuthRequest(BaseModel):
    password: str


_active_tokens: dict[str, float] = {}

REDIS_CLI_PASSWORD = os.environ["REDIS_CLI_PASSWORD"]
MONGO_CLI_PASSWORD = os.environ["MONGO_CLI_PASSWORD"]
TERMINAL_PASSWORD = os.environ["TERMINAL_PASSWORD"]
PYTHON_REPL_PASSWORD = os.environ["PYTHON_REPL_PASSWORD"]
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour


_terminal_executor = TerminalExecutor()
_python_repl_executors: dict[str, PythonReplExecutor] = {}


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
async def execute_redis_command(request: Request, command: Command, x_redis_cli_token: str | None = Header(None)):
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


@router.post("/database/mongo-cli/authenticate", response_class=JSONResponse)
async def authenticate_mongo_cli(auth: AuthRequest):
    """
    Authenticate to access MongoDB CLI.

    Validates the secret password and returns a session token for subsequent requests.
    """
    if not MongoCliExecutor.verify_password(auth.password, MongoCliExecutor.hash_password(MONGO_CLI_PASSWORD)):
        return JSONResponse(content={"success": False, "error": "Invalid password"}, status_code=401)

    token = secrets.token_urlsafe(32)
    _active_tokens[token] = time.time() + TOKEN_EXPIRY_SECONDS

    return JSONResponse(content={"success": True, "token": token, "expires_in": TOKEN_EXPIRY_SECONDS})


@router.get("/database/mongo-cli/verify", response_class=JSONResponse)
async def verify_mongo_cli_session(x_mongo_cli_token: str | None = Header(None)):
    """
    Verify if the current MongoDB CLI session token is valid.

    Used to check authentication status without requiring password re-entry.
    """
    if not _verify_token(x_mongo_cli_token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return JSONResponse(content={"success": True})


@router.post("/database/mongo-cli/execute", response_class=JSONResponse)
async def execute_mongo_command(request: Request, command: Command, x_mongo_cli_token: str | None = Header(None)):
    """
    Execute a MongoDB command securely.

    Requires valid authentication token. Only whitelisted read-only commands are allowed.
    Write operations like insert, update, delete, and drop are blocked.
    """
    if not _verify_token(x_mongo_cli_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if not hasattr(request.app.state, "database_monitor"):
        raise HTTPException(status_code=503, detail="Database monitor not available")

    monitor = request.app.state.database_monitor
    executor = MongoCliExecutor(monitor.mongo_client)

    result = await executor.execute_command(command.command)
    return JSONResponse(content=result)


@router.get("/database/mongo-cli/allowed-commands", response_class=JSONResponse)
async def get_allowed_mongo_commands(request: Request, x_mongo_cli_token: str | None = Header(None)):
    """
    Get list of allowed MongoDB commands.

    Requires authentication. Returns the whitelist of MongoDB commands that can
    be executed through the web interface.
    """
    if not _verify_token(x_mongo_cli_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if not hasattr(request.app.state, "database_monitor"):
        raise HTTPException(status_code=503, detail="Database monitor not available")

    monitor = request.app.state.database_monitor
    executor = MongoCliExecutor(monitor.mongo_client)

    return JSONResponse(content=executor.get_allowed_commands())


@router.get("/database/mongo-cli/collections", response_class=JSONResponse)
async def get_mongo_collections(request: Request, x_mongo_cli_token: str | None = Header(None)):
    """
    Get list of collections in the MongoDB database.

    Requires authentication. Returns all collection names in the database.
    """
    if not _verify_token(x_mongo_cli_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if not hasattr(request.app.state, "database_monitor"):
        raise HTTPException(status_code=503, detail="Database monitor not available")

    monitor = request.app.state.database_monitor
    executor = MongoCliExecutor(monitor.mongo_client)

    collections = await executor.get_collections()
    return JSONResponse(content=collections)


@router.post("/terminal/authenticate", response_class=JSONResponse)
async def authenticate_terminal(auth: AuthRequest):
    """Authenticate to access Terminal."""
    if not TerminalExecutor.verify_password(auth.password, TerminalExecutor.hash_password(TERMINAL_PASSWORD)):
        return JSONResponse(content={"success": False, "error": "Invalid password"}, status_code=401)

    token = secrets.token_urlsafe(32)
    _active_tokens[token] = time.time() + TOKEN_EXPIRY_SECONDS

    return JSONResponse(content={"success": True, "token": token, "expires_in": TOKEN_EXPIRY_SECONDS})


@router.get("/terminal/verify", response_class=JSONResponse)
async def verify_terminal_session(x_terminal_token: str | None = Header(None)):
    """Verify if the current Terminal session token is valid."""
    if not _verify_token(x_terminal_token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return JSONResponse(content={"success": True})


@router.post("/terminal/execute-stream", response_class=StreamingResponse)
async def execute_terminal_command_stream(command: Command, x_terminal_token: str | None = Header(None)):
    """Execute a terminal command securely with streaming output."""
    if not _verify_token(x_terminal_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    async def stream_output():
        async for chunk in _terminal_executor.execute_command_stream(command.command):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(stream_output(), media_type="text/event-stream")

@router.post("/python-repl/execute", response_class=JSONResponse)
async def execute_python_command(request: Request, command: Command, x_python_repl_token: str | None = Header(None)):
    """Execute Python code securely in REPL."""

    if not _verify_token(x_python_repl_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if x_python_repl_token not in _python_repl_executors:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    executor = _python_repl_executors[x_python_repl_token]
    scope = executor._create_scope(request=request, app=request.app)

    result = await executor.execute(command.command, scope=scope)
    return JSONResponse(content=result)

@router.post("/python-repl/authenticate", response_class=JSONResponse)
async def authenticate_python_repl(auth: AuthRequest):
    """Authenticate to access Python REPL."""
    if not PythonReplExecutor.verify_password(auth.password, PythonReplExecutor.hash_password(PYTHON_REPL_PASSWORD)):
        return JSONResponse(content={"success": False, "error": "Invalid password"}, status_code=401)

    token = secrets.token_urlsafe(32)
    _active_tokens[token] = time.time() + TOKEN_EXPIRY_SECONDS
    _python_repl_executors[token] = PythonReplExecutor()

    return JSONResponse(content={"success": True, "token": token, "expires_in": TOKEN_EXPIRY_SECONDS})


@router.get("/python-repl/verify", response_class=JSONResponse)
async def verify_python_repl_session(x_python_repl_token: str | None = Header(None)):
    """Verify if the current Python REPL session token is valid."""
    if not _verify_token(x_python_repl_token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return JSONResponse(content={"success": True})


@router.post("/python-repl/reset", response_class=JSONResponse)
async def reset_python_repl(x_python_repl_token: str | None = Header(None)):
    """Reset Python REPL scope."""
    if not _verify_token(x_python_repl_token):
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")

    if x_python_repl_token in _python_repl_executors:
        _python_repl_executors[x_python_repl_token].reset_scope()

    return JSONResponse(content={"success": True, "message": "REPL scope reset"})


@router.websocket("/system/ws")
async def system_monitor_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time system monitoring.
    """
    await websocket.accept()

    if not hasattr(websocket.app.state, "system_monitor"):
        await websocket.send_json({"error": "System monitor not available"})
        await websocket.close()
        return

    monitor = websocket.app.state.system_monitor

    try:
        while True:
            stats = await monitor.get_all_stats()
            await websocket.send_json(stats)
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        await websocket.close()


@router.get("/system/json", response_class=JSONResponse)
async def system_stats_json(request: Request):
    """
    Get current system statistics in JSON format.

    Returns CPU, memory, disk, network, and PM2 process information.
    """
    if not hasattr(request.app.state, "system_monitor"):
        return {"error": "System monitor not available"}

    monitor = request.app.state.system_monitor
    return await monitor.get_all_stats()
