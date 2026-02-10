from __future__ import annotations

from fastapi import Request
from fastapi.responses import RedirectResponse

from src.app import app


@app.get("/", include_in_schema=False)
async def read_root(request: Request):
    url_for = app.url_path_for("internal_index")
    return RedirectResponse(url=url_for)
