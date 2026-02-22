from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import HTTPException
from starlette.status import HTTP_303_SEE_OTHER

from src.app import app

from .admin_credentials import router as admin_credentials_router
from .admin_dashboard import router as admin_dashboard_router
from .admin_data_manager import router as admin_data_manager_router
from .admin_exercise import router as admin_exercises_router
from .admin_food_items import router as admin_food_items_router
from .admin_login import router as admin_login_router
from .admin_myplan import router as admin_myplan_router
from .admin_songs import router as admin_songs_router
from .admin_tools import router as admin_tools_router
from .admin_users import router as admin_users_router
from .root import router as admin_root_router


def admin_required(request: Request):
    if request.session.get("admin_logged_in"):
        return True
    raise HTTPException(
        status_code=HTTP_303_SEE_OTHER,
        detail="Redirecting to login",
        headers={"Location": app.url_path_for("admin_login_get")},
    )


proxy_admin = APIRouter(prefix="/admin", dependencies=[Depends(admin_required)])

proxy_admin.include_router(admin_root_router)
proxy_admin.include_router(admin_dashboard_router)
proxy_admin.include_router(admin_data_manager_router)
proxy_admin.include_router(admin_tools_router)
proxy_admin.include_router(admin_users_router)
proxy_admin.include_router(admin_credentials_router)
proxy_admin.include_router(admin_food_items_router)
proxy_admin.include_router(admin_songs_router)
proxy_admin.include_router(admin_exercises_router)
proxy_admin.include_router(admin_myplan_router)

router = APIRouter()
router.include_router(proxy_admin)
router.include_router(admin_login_router, prefix="/admin")
