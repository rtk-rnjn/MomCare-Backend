from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.status import (
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from src.app import app

templates: Jinja2Templates = app.state.templates

error_codes = [
    {"code": HTTP_404_NOT_FOUND, "message": "Not Found"},
    {"code": HTTP_500_INTERNAL_SERVER_ERROR, "message": "Internal Server Error"},
    {"code": HTTP_403_FORBIDDEN, "message": "Forbidden"},
]

for error in error_codes:

    @app.exception_handler(error["code"])
    async def not_found_handler(
        request: Request,
        exc: Exception,
    ):
        headers = request.headers
        accept = headers.get("accept", "")

        if accept and "text/html" in accept:
            return templates.TemplateResponse(
                f"errors/{error['code']}.html",
                status_code=error["code"],
                media_type="text/html",
                context={"request": request},
            )

        return JSONResponse(status_code=error["code"], content={"detail": error["message"]}, media_type="application/json")
