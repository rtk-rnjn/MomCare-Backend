from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Path, Query
from fastapi.exceptions import HTTPException
from fastapi.responses import StreamingResponse
from pymongo.asynchronous.collection import AsyncCollection as Collection
from pymongo.asynchronous.database import AsyncDatabase as Database

from src.app import app
from src.models import (
    ExerciseDict,
    ExerciseModel,
    FoodItemDict,
    FoodItemModel,
    SongDict,
    SongModel,
)
from src.utils import S3

from .objects import ServerMessage

database: Database = app.state.mongo_database
s3: S3 = app.state.s3

foods_collection: Collection[FoodItemDict] = database["foods"]
songs_collection: Collection[SongDict] = database["songs"]
exercises_collection: Collection[ExerciseDict] = database["exercises"]

router = APIRouter(prefix="/utils", tags=["Content Utils"])


def _stream(generator):
    return StreamingResponse(generator, media_type="application/json")


async def _get_or_404(collection: Collection, _id: str, label: str):
    doc = await collection.find_one({"_id": _id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"{label} not found.")
    return doc


async def _autocomplete_search(
    *,
    collection: Collection,
    query: str,
    path: str,
    limit: int,
):
    return await collection.aggregate(
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


async def _hydrate_song(song: SongDict) -> SongModel:
    song["song_image_uri"] = await s3.get_presigned_url(f"Songs/{song['mood']}/{song['playlist']}/Image/{song['image_name']}")
    song["playlist_image_uri"] = await s3.get_presigned_url(f"Songs/{song['mood']}/{song['playlist']}/{song['playlist'].lower()}.jpg")
    return SongModel(**song)  # type: ignore


async def _hydrate_exercise(exercise: dict) -> ExerciseModel:
    model = ExerciseModel(**exercise)
    model.image_name_uri = await s3.get_presigned_url(f"ExerciseImages/{model.image_name}")
    return model


async def _search_food(food_name: str, limit: int):
    cursor = await _autocomplete_search(
        collection=foods_collection,
        query=food_name,
        path="name",
        limit=limit,
    )
    async for food in cursor:
        yield FoodItemModel(**food).model_dump_json(by_alias=True) + "\n"


async def _search_exercise(exercise_name: str, limit: int):
    cursor = await _autocomplete_search(
        collection=exercises_collection,
        query=exercise_name,
        path="name",
        limit=limit,
    )
    async for exercise in cursor:
        yield (await _hydrate_exercise(exercise)).model_dump_json(by_alias=True) + "\n"


async def _search_song(text: str):
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
    async for song in cursor:
        yield (await _hydrate_song(song)).model_dump_json(by_alias=True) + "\n"


@router.get(
    "/search/food",
    response_model=list[FoodItemModel],
    response_class=StreamingResponse,
    name="Search Food",
    status_code=200,
    summary="Search for food items",
    description="Search for food items by name. Returns a list of matching food items.",
    responses={
        200: {"description": "Food items retrieved successfully."},
    },
)
async def search_food(
    food_name: str = Query(..., description="Name of the food to search for", example=["Apple"], title="Food Name"),
    limit: int = Query(default=1, description="Maximum number of results to return", example=1, gt=0, title="Result Limit"),
):
    return _stream(_search_food(food_name, limit))


@router.get(
    "/search/song",
    response_model=list[SongModel],
    response_class=StreamingResponse,
    name="Search Song",
    status_code=200,
    summary="Search for songs",
    description="Search for songs by text. Returns a list of matching songs.",
    responses={
        200: {"description": "Songs retrieved successfully."},
    },
)
async def search_song(text: str = Query(..., description="Text to search for in songs", title="Search Text")):
    return _stream(_search_song(text))


@router.get("/search/exercise")
async def search_exercise(exercise_name: str, limit: int = 1):
    return _stream(_search_exercise(exercise_name, limit))


@router.get(
    "/songs",
    name="Get Songs",
    status_code=200,
    response_model=list[SongModel],
    response_description="A list of songs matching the search criteria.",
    summary="Search for songs",
    description="Search for songs based on mood, playlist, author, or title.",
    responses={
        200: {"description": "Songs retrieved successfully."},
    },
)
async def get_songs(
    mood: Literal["happy", "sad", "stressed", "angry"] | None = Query(
        default=None,
        description="Filter songs by mood. Valid values are 'happy', 'sad', 'stressed', and 'angry'.",
    ),
    playlist: str | None = Query(
        default=None,
        description="Filter songs by playlist name.",
    ),
):
    query = {}
    if mood:
        query["mood"] = mood.title()
    if playlist:
        query["playlist"] = playlist

    return [await _hydrate_song(song) for song in await songs_collection.find(query).to_list()]


@router.get(
    "/songs/{song_id}",
    response_model=SongModel,
    response_description="The song matching the provided ID.",
    name="Get Song by ID",
    status_code=200,
    summary="Get song by ID",
    description="Retrieve a song's details by its unique ID.",
    responses={
        200: {"description": "Song retrieved successfully."},
        404: {"description": "Song not found."},
    },
)
async def get_song(
    song_id: str = Path(
        ..., description="The unique ID of the song to retrieve", examples=["123e4567-e89b-12d3-a456-426614174000"], title="Song ID"
    ),
):
    song = await _get_or_404(songs_collection, song_id, "Song")
    return await _hydrate_song(song)


@router.get(
    "/songs/{song_id}/stream",
    response_model=ServerMessage,
    response_description="A message containing the presigned URL to stream the song.",
    name="Stream Song",
    status_code=200,
    summary="Stream song",
    description="Get a presigned URL to stream the song.",
    responses={
        200: {"description": "Presigned URL generated successfully."},
        404: {"description": "Song not found."},
    },
)
async def stream_song(
    song_id: str = Path(
        ..., description="The unique ID of the song to stream", examples=["123e4567-e89b-12d3-a456-426614174000"], title="Song ID"
    ),
):
    song = await _get_or_404(songs_collection, song_id, "Song")
    uri = await s3.get_presigned_url(f"Songs/{song['mood']}/{song['playlist']}/Song/{song['song_name']}")
    return ServerMessage(detail=uri)


@router.get(
    "/exercises/{exercise_id}",
    response_model=ExerciseModel,
    response_description="The exercise matching the provided ID.",
    name="Get Exercise by ID",
    status_code=200,
    summary="Get exercise by ID",
    description="Retrieve an exercise's details by its unique ID.",
    responses={
        200: {"description": "Exercise retrieved successfully."},
        404: {"description": "Exercise not found."},
    },
)
async def get_exercise(
    exercise_id: str = Path(
        ...,
        description="The unique ID of the exercise to retrieve",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Exercise ID",
    ),
):
    exercise = await _get_or_404(exercises_collection, exercise_id, "Exercise")
    return await _hydrate_exercise(exercise)


@router.get(
    "/exercises/{exercise_id}/stream",
    response_model=ServerMessage,
    response_description="A message containing the presigned URL to stream the exercise video.",
    name="Stream Exercise",
    status_code=200,
    summary="Stream exercise video",
    description="Get a presigned URL to stream the exercise video.",
    responses={
        200: {"description": "Presigned URL generated successfully."},
        404: {"description": "Exercise not found."},
    },
)
async def stream_exercise(
    exercise_id: str = Path(
        ...,
        description="The unique ID of the exercise to stream",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Exercise ID",
    ),
):
    exercise = await _get_or_404(exercises_collection, exercise_id, "Exercise")
    uri = await s3.get_presigned_url(f"Exercises/{exercise['name'].lower().replace(' ', '_')}.mp4")
    return ServerMessage(detail=uri)


@router.get(
    "/foods/{food_id}",
    response_model=FoodItemModel,
    response_description="The food item matching the provided ID.",
    name="Get Food by ID",
    status_code=200,
    summary="Get food by ID",
    description="Retrieve a food item's details by its unique ID.",
    responses={
        200: {"description": "Food item retrieved successfully."},
        404: {"description": "Food item not found."},
    },
)
async def get_food(
    food_id: str = Path(
        ...,
        description="The unique ID of the food item to retrieve",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food ID",
    ),
):
    food = await _get_or_404(foods_collection, food_id, "Food item")
    return FoodItemModel(**food)


@router.get(
    "/foods/{food_id}/image",
    response_model=ServerMessage,
    response_description="A message containing the presigned URL to the food item's image.",
    name="Get Food Image",
    status_code=200,
    summary="Get food image",
    description="Retrieve a presigned URL to the food item's image by its unique ID.",
    responses={
        200: {"description": "Presigned URL generated successfully."},
        404: {"description": "Food item not found."},
    },
)
async def get_food_image(
    food_id: str = Path(
        ...,
        description="The unique ID of the food item to retrieve",
        examples=["123e4567-e89b-12d3-a456-426614174000"],
        title="Food ID",
    ),
):
    food = await _get_or_404(foods_collection, food_id, "Food item")
    uri = await s3.get_presigned_url(f"FoodImages/{food['image_name']}")
    return ServerMessage(detail=uri)
