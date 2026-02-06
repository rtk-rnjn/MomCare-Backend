from __future__ import annotations

import asyncio
import os
import logging
import logging.handlers
import rich.logging

import uvicorn
from dotenv import load_dotenv

_ = load_dotenv(verbose=True)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

file_handler = logging.handlers.RotatingFileHandler(
    "app.log", maxBytes=5 * 1024 * 1024, backupCount=2
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

console_handler = rich.logging.RichHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(message)s")
console_handler.setFormatter(console_formatter)

logging.basicConfig(
    level=logging.INFO,
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


def runner():
    uvicorn.run("src.app:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    runner()
