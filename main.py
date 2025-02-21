from __future__ import annotations

import asyncio
import os

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

if __name__ == "__main__":
    import uvicorn

    if DEVELOPMENT:
        uvicorn.run("src:app", host=HOST, port=PORT, reload=True)
    else:
        uvicorn.run(app, host=HOST, port=PORT)
