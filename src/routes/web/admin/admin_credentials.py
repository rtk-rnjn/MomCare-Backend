from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import CredentialsDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

collection: Collection[CredentialsDict] = database["credentials"]

router = APIRouter()

PAGE_SIZE = 20


@router.get("/credentials")
async def admin_credentials(
    request: Request,
    page: int = Query(1, ge=1),
    q: str | None = Query(None),
    provider: str | None = Query(None),
    status: str | None = Query(None),
):

    filter_query: dict = {}

    # 🔍 Search
    if q:
        filter_query["$or"] = [
            {"_id": q},
            {"email_address": {"$regex": q, "$options": "i"}},
            {"email_address_normalized": {"$regex": q, "$options": "i"}},
            {"google_id": {"$regex": q, "$options": "i"}},
            {"apple_id": {"$regex": q, "$options": "i"}},
        ]

    # 🔐 Provider filter
    if provider:
        filter_query["authentication_providers"] = provider

    # 🚦 Status filter
    if status:
        filter_query["account_status"] = status

    total = await collection.count_documents(filter_query)

    cursor = collection.find(filter_query).sort("created_at_timestamp", -1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)

    credentials = await cursor.to_list(length=PAGE_SIZE)

    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "credentials.html.jinja",
        {
            "request": request,
            "credentials": credentials,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "provider": provider or "",
            "status": status or "",
            "total": total,
        },
    )
