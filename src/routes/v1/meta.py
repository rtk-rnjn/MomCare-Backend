from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from src.app import app

router = APIRouter()


@app.get("/", response_class=RedirectResponse, include_in_schema=False)
async def root(request: Request):
    """
    Root endpoint redirecting to API documentation.

    Automatically redirects users to the Swagger UI documentation
    for easy access to API exploration and testing.
    """
    if app.docs_url:
        return RedirectResponse(url=app.docs_url)
