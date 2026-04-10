from __future__ import annotations

import arrow
from dotenv import load_dotenv
from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase as Database
from redis.asyncio import Redis

from src.app import app
from src.routes.api.utils import rate_limiter

load_dotenv()

database: Database = app.state.mongo_database
redis_client: Redis = app.state.redis_client

security = HTTPBearer()

router = APIRouter(prefix="/meta", tags=["System & Meta"], dependencies=[Depends(rate_limiter)])


@router.get("/version", summary="Get API Version", description="Retrieve the current version of the MomCare API.", response_model=str)
async def get_api_version() -> str:
    return app.version


@router.get(
    "/ios-app-version",
    summary="Get iOS App Version",
    description="Retrieve the latest version of the MomCare iOS app.",
    response_model=str,
)
async def get_ios_app_version() -> str:
    return "1.1.0"


@router.get("/status", summary="Get API Status", description="Check the health status of the MomCare API.", response_model=str)
async def get_api_status() -> str:
    return "OK"


@router.get("/uptime", summary="Get API Uptime", description="Retrieve the uptime of the MomCare API in seconds.", response_model=int)
async def get_api_uptime() -> int:
    start_time: arrow.Arrow = app.state.start_time
    now = arrow.utcnow()
    uptime_seconds = (now - start_time).total_seconds()
    return int(uptime_seconds)
