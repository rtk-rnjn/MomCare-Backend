from fastapi import APIRouter

from .internal import *  # noqa
from .v1 import (
    ai_router,
    auth_router,
    content_router,
    database_router,
    otp_router,
)

v1_router = APIRouter(prefix="/v1")

v1_router.include_router(auth_router)
v1_router.include_router(otp_router)
v1_router.include_router(content_router)
v1_router.include_router(ai_router)
v1_router.include_router(database_router)
