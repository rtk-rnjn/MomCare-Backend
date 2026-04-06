from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis

from src.app import app
from src.utils.metrics import collect_runtime_metrics

redis_client: Redis = app.state.redis_client
templates: Jinja2Templates = app.state.templates

router = APIRouter()


@router.get("/metrics", name="admin_metrics", include_in_schema=False)
async def admin_metrics(request: Request, duration_sec: int = Query(300)):
    metrics = await collect_runtime_metrics(redis_client, duration_sec)
    return templates.TemplateResponse("metrics.html.jinja", {"request": request, "metrics": metrics, "duration_sec": duration_sec})
