from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pymongo.collection import Collection
from pymongo.database import Database

from src.app import app
from src.models import (
    ExerciseDict,
    ExerciseModel,
    FoodItemDict,
    FoodItemModel,
    Song,
    SongModel,
)
from src.utils import S3

database: Database = app.state.mongo_database
s3: S3 = app.state.s3

foods_collection: Collection[FoodItemDict] = database["foods"]
songs_collection: Collection[Song] = database["songs"]
exercises_collection: Collection[ExerciseDict] = database["exercises"]

router = APIRouter(prefix="/utils", tags=["Content Utils"])


class ServerMessage(BaseModel):
    detail: str

    class Config:
        extra = "ignore"


def _stream(generator):
    return StreamingResponse(generator, media_type="application/json")


def _get_or_404(collection: Collection, _id: str, label: str):
    doc = collection.find_one({"_id": _id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{label} not found.")
    return doc


def _autocomplete_search(
    *,
    collection: Collection,
    query: str,
    path: str,
    limit: int,
):
    return collection.aggregate(
        [
            {
                "$search": {
                    "index": "default",
                    "autocomplete": {
                        "query": query,
                        "path": path,
                        "fuzzy": {"maxEdits": 1},
                    },
                }
            },
            {"$limit": limit},
        ]
    )


def _hydrate_song(song: Song) -> SongModel:
    song["song_image_uri"] = s3.get_presigned_url(
        f"Songs/{song['mood']}/{song['playlist']}/Image/{song['image_name']}"
    )
    song["playlist_image_uri"] = s3.get_presigned_url(
        f"Songs/{song['mood']}/{song['playlist']}/{song['playlist'].lower()}.jpg"
    )
    return SongModel(**song)  # type: ignore


def _hydrate_exercise(exercise: dict) -> ExerciseModel:
    model = ExerciseModel(**exercise)
    model.image_name_uri = s3.get_presigned_url(f"ExerciseImages/{model.image_name}")
    return model


def _search_food(food_name: str, limit: int):
    cursor = _autocomplete_search(
        collection=foods_collection,
        query=food_name,
        path="name",
        limit=limit,
    )
    for food in cursor:
        yield FoodItemModel(**food).model_dump_json(by_alias=True) + "\n"


def _search_exercise(exercise_name: str, limit: int):
    cursor = _autocomplete_search(
        collection=exercises_collection,
        query=exercise_name,
        path="name",
        limit=limit,
    )
    for exercise in cursor:
        yield _hydrate_exercise(exercise).model_dump_json(by_alias=True) + "\n"


def _search_song(text: str):
    cursor = songs_collection.find(
        {
            "$or": [
                {"mood": {"$regex": text, "$options": "i"}},
                {"playlist": {"$regex": text, "$options": "i"}},
                {"metadata.author": {"$regex": text, "$options": "i"}},
                {"metadata.title": {"$regex": text, "$options": "i"}},
            ]
        }
    )
    for song in cursor:
        yield _hydrate_song(song).model_dump_json(by_alias=True) + "\n"


@router.get("/search/food")
async def search_food(food_name: str, limit: int = 1):
    return _stream(_search_food(food_name, limit))


@router.get("/search/song")
async def search_song(text: str):
    return _stream(_search_song(text))


@router.get("/search/exercise")
async def search_exercise(exercise_name: str, limit: int = 1):
    return _stream(_search_exercise(exercise_name, limit))


@router.get("/songs")
async def get_songs(
    mood: Literal["happy", "sad", "stressed", "angry"] | None = None,
    playlist: str | None = None,
):
    query = {}
    if mood:
        query["mood"] = mood.title()
    if playlist:
        query["playlist"] = playlist

    return [_hydrate_song(song) for song in songs_collection.find(query).to_list()]


@router.get("/songs/{song_id}", response_model=SongModel)
async def get_song(song_id: str):
    song = _get_or_404(songs_collection, song_id, "Song")
    return _hydrate_song(song)


@router.get("/songs/{song_id}/stream", response_model=ServerMessage)
async def stream_song(song_id: str):
    song = _get_or_404(songs_collection, song_id, "Song")
    uri = s3.get_presigned_url(
        f"Songs/{song['mood']}/{song['playlist']}/Song/{song['song_name']}"
    )
    return ServerMessage(detail=uri)


@router.get("/exercises/{exercise_id}", response_model=ExerciseModel)
async def get_exercise(exercise_id: str):
    exercise = _get_or_404(exercises_collection, exercise_id, "Exercise")
    return _hydrate_exercise(exercise)


@router.get("/exercises/{exercise_id}/stream", response_model=ServerMessage)
async def stream_exercise(exercise_id: str):
    exercise = _get_or_404(exercises_collection, exercise_id, "Exercise")
    uri = s3.get_presigned_url(
        f"Exercises/{exercise['name'].lower().replace(' ', '_')}.mp4"
    )
    return ServerMessage(detail=uri)


@router.get("/foods/{food_id}", response_model=FoodItemModel)
async def get_food(food_id: str):
    food = _get_or_404(foods_collection, food_id, "Food item")
    return FoodItemModel(**food)


@router.get("/foods/{food_id}/image", response_model=ServerMessage)
async def get_food_image(food_id: str):
    food = _get_or_404(foods_collection, food_id, "Food item")
    uri = s3.get_presigned_url(f"FoodImages/{food['image_name']}")
    return ServerMessage(detail=uri)
