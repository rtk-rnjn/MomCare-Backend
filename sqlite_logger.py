import logging
import sqlite3
import traceback
import types

with open("log.schema.sql") as schema:
    schema_sql = schema.read()


class _SQLiteLoggingHandler(logging.Handler):
    def __init__(self, level: int = 0):
        super().__init__(level)
        self._db: sqlite3.Connection | None = None

    def connect(self, db_path: str) -> None:
        if self._db is not None:
            return

        self._db = sqlite3.connect(db_path)
        self._db.executescript(schema_sql)
        self._db.commit()
        self._running = True

    def emit(self, record: logging.LogRecord) -> None:
        if self._db is None:
            return

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
                self._format_exc(record.exc_info),  # pyright: ignore[reportArgumentType]
                record.funcName,
                record.stack_info,
            ),
        )
        self._db.commit()

    def shutdown(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
        super().close()

    def _format_exc(self, exc_info: tuple[type[BaseException], BaseException, types.TracebackType] | None) -> str:
        if exc_info is None:
            return "<no traceback>"

        return "".join(traceback.format_exception(*exc_info))
