from __future__ import annotations

import asyncio
import logging
import logging.handlers
import os

import rich.logging
import uvicorn
from dotenv import load_dotenv
from rich.traceback import install as install_rich_traceback

load_dotenv()
install_rich_traceback()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.disabled = True
uvicorn_access_logger.propagate = False

uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.setLevel(logging.INFO)

file_handler = logging.handlers.RotatingFileHandler("app.log", maxBytes=5 * 1024 * 1024, backupCount=2)
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

console_handler = rich.logging.RichHandler(level=logging.INFO)
console_formatter = logging.Formatter("%(message)s")
console_handler.setFormatter(console_formatter)

logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler],
)

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass


def runner(*, host: str = HOST, port: int = PORT) -> None:
    development_mode = os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
    if development_mode:
        logging.info("Running in development mode with auto-reload enabled.")
        uvicorn.run("src.app:app", host=host, port=port, reload=True)
    else:
        uvicorn.run("src.app:app", host=host, port=port)


if __name__ == "__main__":
    runner()
