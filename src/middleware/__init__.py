from __future__ import annotations

import uuid
from time import perf_counter
from typing import Awaitable, Callable

import arrow
import orjson
from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from redis.asyncio import Redis
from starlette.responses import Response

from src.app import app

from .logger import ConsoleLoggingMiddleware

redis_client: Redis = app.state.redis_client
LOGS_CHANNEL_NAME = "request_logs"

__all__ = ["ConsoleLoggingMiddleware"]


@app.middleware("http")
async def add_process_time_header(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    start_time = perf_counter()
    response = await call_next(request)
    process_time = perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)

    ip_addr = request.client.host if request.client else "unknown"
    status_code = response.status_code

    payload = {
        "request_id": str(uuid.uuid4()),
        "timestamp": arrow.utcnow().isoformat(),
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "process_time": process_time,
        "client_ip": ip_addr,
    }

    await redis_client.publish(LOGS_CHANNEL_NAME, orjson.dumps(payload))

    return response


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(LOGS_CHANNEL_NAME)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            data = message["data"]
            await websocket.send_bytes(data)

    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(LOGS_CHANNEL_NAME)
        await pubsub.close()


app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ConsoleLoggingMiddleware)
