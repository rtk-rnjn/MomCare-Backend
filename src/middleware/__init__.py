from __future__ import annotations

import os
from typing import NotRequired, TypedDict

from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.app import app

from .logger import ConsoleLoggingMiddleware

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
