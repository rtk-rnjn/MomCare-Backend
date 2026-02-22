from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import FoodItemDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

collection: Collection[FoodItemDict] = database["foods"]


router = APIRouter()

PAGE_SIZE = 20


@router.get("/food-items")
async def admin_food_items(
    request: Request,
    page: int = Query(1, ge=1),
    q: str | None = Query(None),
    state: str | None = Query(None),
    food_type: str | None = Query(None),
):
    filter_query: dict = {}

    if q:
        filter_query["name"] = {"$regex": q, "$options": "i"}

    if state:
        filter_query["state"] = state

    if food_type:
        filter_query["type"] = food_type

    total = await collection.count_documents(filter_query)

    cursor = collection.find(filter_query).sort("name", 1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)

    food_items = await cursor.to_list(length=PAGE_SIZE)

    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "food_items.html.jinja",
        {
            "request": request,
            "items": food_items,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "state": state or "",
            "food_type": food_type or "",
            "total": total,
        },
    )
