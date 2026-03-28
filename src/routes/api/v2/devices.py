from __future__ import annotations

import arrow
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from starlette.status import HTTP_200_OK

from src.app import app
from src.routes.api.utils import get_user_id

router: APIRouter = APIRouter(prefix="/devices", tags=["Devices"])

redis_client: Redis = app.state.redis_client


class ErrorDetailModel(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ErrorResponseModel(BaseModel):
    detail: list[ErrorDetailModel] | str


@router.post(
    "/apns",
    summary="Register APNs Device Token",
    name="Register APNs Device Token",
    description="Register a device token for Apple Push Notification Service (APNs) to receive push notifications on iOS devices.",
    response_model=bool,
    response_description="Always returns true if the device token was successfully registered.",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "description": "Device token stored.",
            "content": {"application/json": {"example": True}},
        },
    },
)
async def register_device_token(
    device_token: str = Body(..., embed=True), user_id: str = Depends(get_user_id, use_cache=False)
) -> bool:
    await redis_client.set(f"device_token:{user_id}", device_token)
    return True


@router.delete(
    "/apns",
    summary="Unregister APNs Device Token",
    name="Unregister APNs Device Token",
    description="Unregister a device token for Apple Push Notification Service (APNs) to stop receiving push notifications on iOS devices.",
    response_model=bool,
    response_description="Always returns true if the device token was successfully unregistered.",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "description": "Device token removed.",
            "content": {"application/json": {"example": True}},
        },
    },
)
async def unregister_device_token(user_id: str = Depends(get_user_id, use_cache=False)) -> bool:
    await redis_client.delete(f"device_token:{user_id}")
    return True


@router.post(
    "/daily-metrics",
    summary="Data receiving endpoint from `MXMetricManagerSubscriber` in iOS app",
    name="Receive Daily Metrics",
    description="Endpoint to receive daily metrics data from the iOS app using `MXMetricManagerSubscriber`.",
    response_model=bool,
    response_description="Always returns true if the metrics data was successfully received.",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "description": "Metrics data received.",
            "content": {"application/json": {"example": True}},
        },
    },
    include_in_schema=False,
)
async def receive_daily_metrics(data: dict = Body(..., embed=False), user_id: str = Depends(get_user_id, use_cache=False)) -> bool:
    timestamp = arrow.now().int_timestamp

    await redis_client.set(f"daily_metrics:{user_id}:{timestamp}", str(data))
    return True


@router.post(
    "/diagnostic-metrics",
    summary="Data receiving endpoint from `MXMetricManagerSubscriber` in iOS app",
    name="Receive Diagnostic Metrics",
    description="Endpoint to receive diagnostic metrics data from the iOS app using `MXMetricManagerSubscriber`.",
    response_model=bool,
    response_description="Always returns true if the metrics data was successfully received.",
    status_code=HTTP_200_OK,
    responses={
        HTTP_200_OK: {
            "description": "Metrics data received.",
            "content": {"application/json": {"example": True}},
        },
    },
    include_in_schema=False,
)
async def receive_diagnostic_metrics(
    data: dict = Body(..., embed=False), user_id: str = Depends(get_user_id, use_cache=False)
) -> bool:
    timestamp = arrow.now().int_timestamp

    await redis_client.set(f"diagnostic_metrics:{user_id}:{timestamp}", str(data))
    return True
