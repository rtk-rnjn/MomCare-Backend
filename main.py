from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import traceback
import types

import aiosqlite
from rich.logging import RichHandler

from src import app

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DEVELOPMENT = os.getenv("DEVELOPMENT", "True").lower() == "true"

with open("log.schema.sql") as schema:
    schema_sql = schema.read()

import asyncio
import logging
from collections import deque

import aiosqlite


class _SQLiteLoggingHandler(logging.Handler):
    def __init__(self, level=0, buffer_size=100, flush_interval=5):
        super().__init__(level)
        self._db: aiosqlite.Connection | None = None
        self._buffer = deque()
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._running = False

    async def connect(self, db_path: str) -> None:
        if self._db is not None:
            return

        self._db = await aiosqlite.connect(db_path)
        await self._db.executescript(schema_sql)
        await self._db.commit()
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    def emit(self, record: logging.LogRecord) -> None:
        if self._db is None:
            return

        # Must be threadsafe (emit may be called from sync code)
        asyncio.create_task(self._enqueue(record))

    async def _enqueue(self, record: logging.LogRecord) -> None:
        async with self._lock:
            self._buffer.append(record)
            if len(self._buffer) >= self._buffer_size:
                await self._flush()

    async def _flush_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self._flush_interval)
            async with self._lock:
                if self._buffer:
                    await self._flush()

    async def _flush(self) -> None:
        if not self._db:
            return
        records = list(self._buffer)
        self._buffer.clear()

        async with self._db.executemany(
            """
            INSERT INTO logs (name, level, pathname, lineno, message, exc_info, func, sinfo) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.name,
                    r.levelno,
                    r.pathname,
                    r.lineno,
                    r.getMessage(),
                    self._format_exc(r.exc_info),
                    r.funcName,
                    r.stack_info,
                )
                for r in records
            ],
        ):
            pass
        await self._db.commit()

    async def shutdown(self) -> None:
        self._running = False
        if self._flush_task:
            await self._flush_task
        async with self._lock:
            if self._buffer:
                await self._flush()
        if self._db:
            await self._db.close()
            self._db = None
        super().close()

    def _format_exc(self, exc_info: tuple[type[BaseException], BaseException, types.TracebackType] | None) -> str:
        if exc_info is None:
            return "<no traceback>"

        return "".join(traceback.format_exception(*exc_info))


sqlite_handler = _SQLiteLoggingHandler()

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(), sqlite_handler])

LOGGING_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"custom": {"()": RichHandler}},
}

setattr(app, "sqlite_handler", sqlite_handler)

if __name__ == "__main__":
    import uvicorn

    if DEVELOPMENT:
        uvicorn.run("src:app", host=HOST, port=PORT, reload=True, log_config=LOGGING_CONFIG)
    else:
        uvicorn.run(app, host=HOST, port=PORT, log_config=LOGGING_CONFIG)
