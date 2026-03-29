from __future__ import annotations

from fastapi import APIRouter

from .generate import router as generate_router
from .search import router as search_router

router = APIRouter(prefix="/ai", tags=["AI Content"])

router.include_router(search_router)
router.include_router(generate_router)
