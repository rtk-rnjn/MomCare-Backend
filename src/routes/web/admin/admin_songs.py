from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import SongDict

database: Database = app.state.mongo_database
templates: Jinja2Templates = app.state.templates

collection: Collection[SongDict] = database["songs"]

router = APIRouter()

PAGE_SIZE = 20


@router.get("/songs")
async def admin_songs(
    request: Request,
    page: int = Query(1, ge=1),
    q: str | None = Query(None),
    mood: str | None = Query(None),
    playlist: str | None = Query(None),
):
    filter_query: dict = {}

    # 🔍 Search by song_name, author, or title
    if q:
        filter_query["$or"] = [
            {"song_name": {"$regex": q, "$options": "i"}},
            {"metadata.author": {"$regex": q, "$options": "i"}},
            {"metadata.title": {"$regex": q, "$options": "i"}},
        ]

    # 🎵 Mood filter
    if mood:
        filter_query["mood"] = mood

    # 📂 Playlist filter
    if playlist:
        filter_query["playlist"] = {"$regex": playlist, "$options": "i"}

    total = await collection.count_documents(filter_query)

    cursor = collection.find(filter_query).sort("song_name", 1).skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)

    songs = await cursor.to_list(length=PAGE_SIZE)
    total_pages = max(1, ceil(total / PAGE_SIZE))

    return templates.TemplateResponse(
        "songs.html.jinja",
        {
            "request": request,
            "songs": songs,
            "page": page,
            "total_pages": total_pages,
            "q": q or "",
            "mood": mood or "",
            "playlist": playlist or "",
            "total": total,
        },
    )
