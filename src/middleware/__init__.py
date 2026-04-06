from __future__ import annotations

import asyncio
import inspect
import logging
import os
import sys
import time
import traceback
import uuid
from contextlib import suppress
from time import perf_counter
from typing import Awaitable, Callable, NotRequired, TypedDict

import arrow
import orjson
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from src.app import app
from src.utils.metrics import collect_runtime_metrics

from .logger import ConsoleLoggingMiddleware

redis_client: Redis = app.state.redis_client
LOGS_CHANNEL_NAME = "request_logs"
METRICS_REQUESTS_TOTAL_KEY = "metrics:requests:total"
METRICS_REQUESTS_PER_SEC_KEY_PREFIX = "metrics:requests:sec"
METRICS_STATUS_KEY_PREFIX = "metrics:status"
METRICS_ENDPOINT_REQUESTS_KEY = "metrics:endpoint_requests"
METRICS_ENDPOINT_STATUS_KEY = "metrics:endpoint_status"
METRICS_ENDPOINT_STATUS_PER_SEC_PREFIX = "metrics:endpoint_status:sec"
METRICS_ENDPOINT_FAILURES_KEY = "metrics:endpoint_failures"
METRICS_ENDPOINT_LAST_ERROR_KEY = "metrics:endpoint_last_error"

__all__ = ["ConsoleLoggingMiddleware"]


class RedisStreamLogPayload(TypedDict):
    request_id: str
    timestamp: str
    kind: str
    level: str
    logger_name: str
    message: str
    module: str
    function: str
    line: int
    pathname: str
    thread: str | None
    process: str
    exception: NotRequired[str]


class HTTPLogPayload(TypedDict):
    request_id: str
    timestamp: str
    kind: str
    level: str
    logger_name: str
    message: str
    method: str
    path: str
    status_code: int
    process_time: float
    client_ip: str
    exception: NotRequired[str]


class RedisStreamLogHandler(logging.Handler):
    def __init__(self, redis: Redis, loop: asyncio.AbstractEventLoop):
        super().__init__(level=logging.NOTSET)
        self.redis = redis
        self.loop = loop

    async def _publish(self, payload: RedisStreamLogPayload) -> None:
        await self.redis.publish(LOGS_CHANNEL_NAME, orjson.dumps(payload))

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("redis") or record.name.startswith("asyncio"):
            return

        try:
            payload = RedisStreamLogPayload(
                request_id=str(uuid.uuid4()),
                timestamp=arrow.utcnow().isoformat(),
                kind="log",
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                module=record.module,
                function=record.funcName,
                line=record.lineno,
                pathname=record.pathname,
                thread=record.threadName,
                process=str(record.process),
            )

            if record.exc_info:
                formatter = logging.Formatter()
                payload["exception"] = formatter.formatException(record.exc_info)

            try:
                running_loop = asyncio.get_running_loop()
                if running_loop is self.loop:
                    running_loop.create_task(self._publish(payload))
                else:
                    asyncio.run_coroutine_threadsafe(self._publish(payload), self.loop)
            except RuntimeError:
                asyncio.run_coroutine_threadsafe(self._publish(payload), self.loop)

        except Exception:
            pass


def setup_stream_logging(app: FastAPI) -> None:
    if getattr(app.state, "stream_logging_configured", False):
        return

    loop = asyncio.get_running_loop()
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    handler = RedisStreamLogHandler(redis=redis_client, loop=loop)
    root_logger.addHandler(handler)

    logging.captureWarnings(True)
    app.state.stream_logging_configured = True


def _unhandled_exception_hook(exc_type, exc_value, exc_traceback) -> None:
    logging.getLogger("unhandled").critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = _unhandled_exception_hook


def get_log_level(status_code: int) -> str:
    if status_code >= 500:
        return "ERROR"
    if status_code >= 400:
        return "WARNING"
    if status_code >= 300:
        return "INFO"
    return "INFO"


async def _record_request_metrics(request: Request, status_code: int, payload: HTTPLogPayload) -> None:
    endpoint = f"{request.method} {request.url.path}"
    current_second = int(time.time())
    per_second_key = f"{METRICS_REQUESTS_PER_SEC_KEY_PREFIX}:{current_second}"

    await redis_client.incr(METRICS_REQUESTS_TOTAL_KEY)
    await redis_client.incr(per_second_key)
    await redis_client.expire(per_second_key, 180)

    await redis_client.incr(f"{METRICS_STATUS_KEY_PREFIX}:{status_code}")
    maybe_awaitable = redis_client.hincrby(METRICS_ENDPOINT_REQUESTS_KEY, endpoint, 1)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable

    maybe_awaitable = redis_client.hincrby(METRICS_ENDPOINT_STATUS_KEY, f"{endpoint}|{status_code}", 1)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable

    endpoint_sec_key = f"{METRICS_ENDPOINT_STATUS_PER_SEC_PREFIX}:{current_second}"
    maybe_awaitable = redis_client.hincrby(endpoint_sec_key, f"{endpoint}|{status_code}", 1)
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable

    await redis_client.expire(endpoint_sec_key, 7200)

    if status_code >= 400:
        await redis_client.incr(f"{METRICS_STATUS_KEY_PREFIX}:4xx")
        maybe_awaitable = redis_client.hincrby(METRICS_ENDPOINT_FAILURES_KEY, endpoint, 1)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    if status_code >= 500:
        await redis_client.incr(f"{METRICS_STATUS_KEY_PREFIX}:5xx")

    last_error_payload = {
        "timestamp": payload.get("timestamp"),
        "status_code": status_code,
        "message": payload.get("message"),
        "path": payload.get("path"),
        "method": payload.get("method"),
        "traceback": payload.get("exception"),
    }
    if status_code >= 400:
        maybe_awaitable = redis_client.hset(
            METRICS_ENDPOINT_LAST_ERROR_KEY, endpoint, orjson.dumps(last_error_payload).decode("utf-8")
        )
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable


@app.middleware("http")
async def add_process_time_header(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    start_time = perf_counter()
    ip_addr = request.client.host if request.client else "unknown"

    payload: HTTPLogPayload = {
        "request_id": str(uuid.uuid4()),
        "timestamp": arrow.utcnow().isoformat(),
        "kind": "request",
        "level": "",
        "logger_name": "http.request",
        "message": "",
        "method": request.method,
        "path": request.url.path,
        "status_code": 0,
        "process_time": 0.0,
        "client_ip": ip_addr,
    }
    try:
        response = await call_next(request)
        process_time = perf_counter() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = payload["request_id"]

        status_code = response.status_code

        payload["level"] = get_log_level(status_code)
        payload["message"] = f"{request.method} {request.url.path} -> {status_code}"
        payload["status_code"] = status_code
        payload["process_time"] = process_time

        try:
            await _record_request_metrics(request, status_code, payload)
            await redis_client.publish(LOGS_CHANNEL_NAME, orjson.dumps(payload))
        except Exception:
            pass

        return response

    except Exception as http_error:
        process_time = perf_counter() - start_time
        status_code = 500
        tb = traceback.format_exc()

        payload["level"] = "ERROR"
        payload["message"] = f"{request.method} {request.url.path} -> {status_code} (Unhandled Exception)"
        payload["status_code"] = status_code
        payload["process_time"] = process_time
        payload["exception"] = tb

        try:
            await _record_request_metrics(request, status_code, payload)
            await redis_client.publish(LOGS_CHANNEL_NAME, orjson.dumps(payload))
        except Exception as logging_error:
            raise logging_error from http_error

        raise http_error


async def websocket_logs(websocket: WebSocket):
    await websocket.accept()

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(LOGS_CHANNEL_NAME)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            data = message["data"]
            if isinstance(data, bytes):
                await websocket.send_text(data.decode("utf-8"))
            else:
                await websocket.send_text(str(data))

    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(LOGS_CHANNEL_NAME)
        await pubsub.close()


async def _stream_metrics(websocket: WebSocket, get_duration: Callable[[], int]) -> None:
    while True:
        try:
            metrics = await collect_runtime_metrics(redis_client, get_duration())
            await websocket.send_text(orjson.dumps(metrics).decode("utf-8"))
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            break


async def websocket_metrics(websocket: WebSocket):
    await websocket.accept()
    duration_sec = 300

    sender = asyncio.create_task(_stream_metrics(websocket, lambda: duration_sec))

    try:
        async for message in websocket.iter_text():
            try:
                payload = orjson.loads(message)
                if isinstance(payload, dict) and "duration_sec" in payload:
                    duration_sec = int(payload["duration_sec"])
            except Exception:
                continue
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with suppress(asyncio.CancelledError):
            await sender


app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET_KEY"], max_age=60 * 30)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ConsoleLoggingMiddleware)
