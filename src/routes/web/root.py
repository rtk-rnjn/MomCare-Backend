from __future__ import annotations

from fastapi import Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates

from src.app import FRONTEND_DIR, app

templates: Jinja2Templates = app.state.templates


@app.get("/", include_in_schema=False)
async def read_root(request: Request):
    return FileResponse(FRONTEND_DIR / "dist" / "index.html")


@app.get("/spotlight", include_in_schema=False)
async def spotlight(request: Request):
    return templates.TemplateResponse("framework.html", {"request": request, "framework": "spotlight"})


@app.get("/rapidoc", include_in_schema=False)
async def rapidoc(request: Request):
    return templates.TemplateResponse("framework.html", {"request": request, "framework": "rapidoc"})
