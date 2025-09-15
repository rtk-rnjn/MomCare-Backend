from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

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


@router.get("/", response_model=dict[Literal["name", "version", "description", "docs_url", "redoc_url", "openapi_url"], str | None])
async def get_meta(request: Request):
    """
    Get API metadata and configuration information.

    Provides basic information about the API including version,
    available documentation endpoints, and service description.
    """
    return {
        "name": app.title,
        "version": app.version,
        "description": app.description,
        "docs_url": app.docs_url,
        "redoc_url": app.redoc_url,
        "openapi_url": app.openapi_url,
    }


@router.get("/health", response_model=dict[Literal["status"], Literal["healthy"]])
async def get_health(request: Request):
    """
    Health check endpoint for service monitoring.

    Simple endpoint to verify that the API service is running and responsive.
    Used by load balancers, monitoring systems, and deployment tools.
    """
    return {"status": "healthy"}


@router.get("/version", response_model=dict[Literal["version"], str])
async def get_version(request: Request):
    """
    Get current API version information.

    Returns the current version of the API for client applications
    to verify compatibility and feature availability.
    """
    return {"version": app.version}


@router.get("/ping", response_model=dict[Literal["ping"], Literal["pong"]])
async def get_ping(request: Request):
    """
    Simple ping endpoint for connectivity testing.

    Basic connectivity test endpoint that responds immediately
    to verify network connectivity and basic service responsiveness.
    """
    return {"ping": "pong"}


app.include_router(router, prefix="/meta", tags=["System & Meta"])
