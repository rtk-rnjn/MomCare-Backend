from fastapi import APIRouter

from .api import v1_ai_router, v1_auth_router, v1_update_router, v1_utils_router

api_router = APIRouter(prefix="/api")

api_router.include_router(v1_auth_router, prefix="/v1")
api_router.include_router(v1_ai_router, prefix="/v1")
api_router.include_router(v1_utils_router, prefix="/v1")
api_router.include_router(v1_update_router, prefix="/v1")

__all__ = ("api_router",)
