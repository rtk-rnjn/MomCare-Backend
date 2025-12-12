from __future__ import annotations

import asyncio
import logging
import os

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

HOST = os.getenv("HOST", "0.0.0.0")  # nosec B104
PORT = int(os.getenv("PORT", 8000))
DEVELOPMENT = os.getenv("DEVELOPMENT", "True").lower() == "true"


logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler()])

LOGGING_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"custom": {"()": RichHandler}},
}

if __name__ == "__main__":
    import uvicorn

    if DEVELOPMENT:
        uvicorn.run("src:app", host=HOST, port=PORT, reload=True, log_config=LOGGING_CONFIG)
    else:
        uvicorn.run(app, host=HOST, port=PORT, log_config=LOGGING_CONFIG)
