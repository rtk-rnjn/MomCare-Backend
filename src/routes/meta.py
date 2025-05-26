from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from src.app import app, redis_client, mongo_client

router = APIRouter()


@app.route("/")
async def root(request: Request):
    if app.docs_url:
        return RedirectResponse(url=app.docs_url)

    return {"message": "Welcome to the API!"}


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
    start_time = perf_counter()
    await redis_client.ping()
    end_time = perf_counter()

    redis_ping = end_time - start_time

    start_time = perf_counter()
    await mongo_client.admin.command("ping")
    end_time = perf_counter()
    mongo_ping = end_time - start_time


    return {
        "ping": "pong",
        "redis": redis_ping,
        "mongo": mongo_ping
    }


app.include_router(router, prefix="/meta", tags=["Meta"])
