from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .db_tools import router as db_tools_router
from .logs import router as logs_router
from .manage import router as manage_router
from .models import router as models_router
from .system import router as system_router
from .users import router as users_router

admin_router = APIRouter(prefix="/admin")

admin_router.include_router(auth_router)
admin_router.include_router(manage_router)
admin_router.include_router(users_router)
admin_router.include_router(models_router)
admin_router.include_router(logs_router)
admin_router.include_router(db_tools_router)
admin_router.include_router(system_router)

__all__ = ("admin_router",)
