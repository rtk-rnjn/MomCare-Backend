from fastapi import APIRouter

from .api import (
    v1_ai_router,
    v1_auth_router,
    v1_update_router,
    v1_utils_router,
    v2_auth_router,
    v2_devices_router,
)
from .web import index_router

api_router = APIRouter(prefix="/api")
web_router = APIRouter(include_in_schema=False)

v1_router = APIRouter(prefix="/v1")
v2_router = APIRouter(prefix="/v2")

v1_router.include_router(v1_ai_router)
v1_router.include_router(v1_auth_router)
v1_router.include_router(v1_update_router)
v1_router.include_router(v1_utils_router)

v2_router.include_router(v2_auth_router)
v2_router.include_router(v2_devices_router)

api_router.include_router(v1_router)
api_router.include_router(v2_router)

web_router.include_router(index_router)

__all__ = ("api_router", "web_router")
