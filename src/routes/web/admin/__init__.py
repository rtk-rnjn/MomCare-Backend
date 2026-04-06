from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.utils.admin_auth import get_admin_session

from .accounts import router as admin_accounts_router
from .audit import router as admin_audit_router
from .credentials import router as admin_credentials_router
from .dashboard import router as admin_dashboard_router
from .data_manager import router as admin_data_manager_router
from .login import router as admin_login_router
from .logs import router as admin_logs_router
from .metrics_view import router as admin_metrics_router
from .root import router as admin_root_router
from .users import router as admin_users_router


def _admin_required(request: Request):
    return get_admin_session(request)


proxy_admin = APIRouter(prefix="/admin-dashboard", dependencies=[Depends(_admin_required)])

proxy_admin.include_router(admin_root_router)
proxy_admin.include_router(admin_dashboard_router)
proxy_admin.include_router(admin_data_manager_router)
proxy_admin.include_router(admin_users_router)
proxy_admin.include_router(admin_credentials_router)
proxy_admin.include_router(admin_logs_router)
proxy_admin.include_router(admin_audit_router)
proxy_admin.include_router(admin_metrics_router)
proxy_admin.include_router(admin_accounts_router)

router = APIRouter()
router.include_router(proxy_admin)
router.include_router(admin_login_router, prefix="/admin-dashboard")
