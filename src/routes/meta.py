from __future__ import annotations

from fastapi import APIRouter, Request

from src.app import app, genai_handler

router = APIRouter()


@router.get("/")
async def get_meta(request: Request):
    return {
        "name": app.title,
        "version": app.version,
        "description": app.description,
        "docs_url": app.docs_url,
        "redoc_url": app.redoc_url,
        "openapi_url": app.openapi_url,
    }


@router.get("/health")
async def get_health(request: Request):
    return {"status": "healthy"}


@router.get("/version")
async def get_version(request: Request):
    return {"version": app.version}


@router.get("/ping")
async def get_ping(request: Request):
    return {"ping": "pong"}


app.include_router(router, prefix="/meta", tags=["meta"])


@app.get("/test")
async def test(request: Request):
    await genai_handler.generate_response(user_id="31E09985-468F-4308-B0AE-1D4B5A5B6330")
