from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import MyPlanDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

collection: Collection[MyPlanDict] = database["plans"]


router = APIRouter()

PAGE_SIZE = 20


@router.get("/myplan")
async def admin_myplan(
    request: Request,
    page: int = Query(1, ge=1),
    q: str | None = Query(None),  # search by user name/email
):
    plans_collection = collection

    pipeline = []

    pipeline.append({"$lookup": {"from": "users", "localField": "user_id", "foreignField": "_id", "as": "user"}})
    pipeline.append({"$unwind": "$user"})

    if q:
        pipeline.append(
            {
                "$match": {
                    "$or": [
                        {"user.first_name": {"$regex": q, "$options": "i"}},
                        {"user.last_name": {"$regex": q, "$options": "i"}},
                        {"user.phone_number": {"$regex": q, "$options": "i"}},
                    ]
                }
            }
        )

    # Sort by created_at descending
    pipeline.append({"$sort": {"created_at_timestamp": -1}})

    # Count total
    count_pipeline = pipeline + [{"$count": "total"}]
    cursor = await plans_collection.aggregate(count_pipeline)
    count_result = await cursor.to_list(length=1)
    total = count_result[0]["total"] if count_result else 0  # type: ignore

    # Pagination
    pipeline.append({"$skip": (page - 1) * PAGE_SIZE})
    pipeline.append({"$limit": PAGE_SIZE})

    # Lookup food details for each meal
    for meal in ["breakfast", "lunch", "dinner", "snacks"]:
        pipeline.append({"$lookup": {"from": "foods", "localField": f"{meal}.food_id", "foreignField": "_id", "as": f"{meal}_food"}})

    # Execute aggregation
    plans_cursor = await plans_collection.aggregate(pipeline)
    plans = await plans_cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "myplan.html.jinja",
        {
            "request": request,
            "plans": plans,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "total": total,
        },
    )
