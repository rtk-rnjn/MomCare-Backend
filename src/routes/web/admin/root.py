from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
async def admin_root(request: Request):
    return RedirectResponse(url=request.url_for("admin_dashboard"), status_code=307)
