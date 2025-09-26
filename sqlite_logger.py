import logging
import queue
import sqlite3
import threading
import traceback
import types

with open("log.schema.sql") as schema:
    schema_sql = schema.read()


class _SQLiteLoggingHandler(logging.Handler):
    def __init__(self, level: int = 0):
        super().__init__(level)
        self._db: sqlite3.Connection | None = None
        self._queue: queue.Queue[logging.LogRecord] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    def connect(self, db_path: str) -> None:
        if self._db is not None:
            return

        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.executescript(schema_sql)
        self._db.commit()

        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def emit(self, record: logging.LogRecord) -> None:
        if self._db is None:
            return
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            pass  # drop log if queue is full

    def _worker(self) -> None:
        while self._running or not self._queue.empty():
            try:
                record = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._flush(record)

    def _flush(self, record: logging.LogRecord) -> None:
        if not self._db:
            return

        self._db.execute(
            """
            INSERT INTO logs (name, level, pathname, lineno, message, exc_info, func, sinfo) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.name,
                record.levelno,
                record.pathname,
                record.lineno,
                record.getMessage(),
                self._format_exc(record.exc_info),  # type: ignore
                record.funcName,
                record.stack_info,
            ),
        )
        self._db.commit()

    def fetch_logs(self, limit: int, offset: int) -> list[list]:
        if not self._db:
            return []

        cursor = self._db.execute(
            """
            SELECT id, name, level, pathname, lineno, message, exc_info, func, sinfo, created_at
            FROM logs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        return rows

    def shutdown(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join()
        if self._db is not None:
            self._db.close()
            self._db = None
        super().close()

    def _format_exc(
        self,
        exc_info: tuple[type[BaseException], BaseException, types.TracebackType] | None,
    ) -> str:
        if exc_info is None:
            return "<no traceback>"
        return "".join(traceback.format_exception(*exc_info))
