from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from redis.asyncio import Redis
from starlette.status import HTTP_200_OK

from src.app import app
from src.routes.api.utils import get_user_id

router: APIRouter = APIRouter(prefix="/devices", tags=["Devices"])

redis_client: Redis = app.state.redis_client


@router.post(
    "/apns",
    summary="Register APNs Device Token",
    name="Register APNs Device Token",
    description="Register a device token for Apple Push Notification Service (APNs) to receive push notifications on iOS devices.",
    response_model=bool,
    response_description="Always returns true if the device token was successfully registered.",
    status_code=HTTP_200_OK,
)
async def register_device_token(
    device_token: str = Body(..., embed=True), user_id: str = Depends(get_user_id, use_cache=False)
) -> bool:
    await redis_client.set(f"device_token:{user_id}", device_token)
    return True
