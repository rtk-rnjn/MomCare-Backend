from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import UserDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

collection: Collection[UserDict] = database["users"]

router = APIRouter()

PAGE_SIZE = 20


@router.get("/users", include_in_schema=False)
async def admin_users(request: Request, page: int = Query(1, ge=1), q: str | None = Query(None)):
    filter_query = {}

    if q is not None:
        filter_query["$or"] = [
            {"_id": q},
            {"first_name": {"$regex": q, "$options": "i"}},
            {"last_name": {"$regex": q, "$options": "i"}},
            {"phone_number": {"$regex": q, "$options": "i"}},
        ]

    total = await collection.count_documents(filter_query)
    cursor = collection.find(filter_query).sort("created_at_timestamp", -1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    users = await cursor.to_list(length=PAGE_SIZE)

    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "users.html.jinja",
        {
            "request": request,
            "users": users,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "total": total,
        },
    )
