from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import ExerciseDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

collection: Collection[ExerciseDict] = database["exercises"]


router = APIRouter()

PAGE_SIZE = 20


@router.get("/exercise")
async def admin_exercise(
    request: Request,
    page: int = Query(1, ge=1),
    q: str | None = Query(None),
    level: str | None = Query(None),
    week: str | None = Query(None),
):

    filter_query: dict = {}

    # 🔍 Search by name or tags
    if q:
        filter_query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"tags": {"$regex": q, "$options": "i"}}]

    # 🏋️ Level filter
    if level:
        filter_query["level"] = level

    # 📆 Week filter
    if week:
        filter_query["week"] = {"$regex": week, "$options": "i"}

    total = await collection.count_documents(filter_query)

    cursor = collection.find(filter_query).sort("name", 1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)

    exercises = await cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "exercise.html.jinja",
        {
            "request": request,
            "exercises": exercises,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "level": level or "",
            "week": week or "",
            "total": total,
        },
    )
