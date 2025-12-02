from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.app import genai_handler, pixelbay_image_fetcher, s3_client
from src.routes.utils import data_handler
from src.static.quotes import ANGRY_QUOTES, HAPPY_QUOTES, SAD_QUOTES, STRESSED_QUOTES
from src.utils import Finder, Symptom, TrimesterData

if TYPE_CHECKING:
    from typing_extensions import AsyncIterator


finder = Finder()


router = APIRouter(prefix="/content", tags=["Content Management"])
VALID_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]
VALID_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mp3"]
VALID_EXTENSIONS = VALID_IMAGE_EXTENSIONS + VALID_VIDEO_EXTENSIONS


class S3Response(BaseModel):
    """
    Response containing S3 file access information.

    Provides secure links to file content with expiry information for temporary access.
    """

    link: str = Field(
        ...,
        description="Pre-signed URL for file access",
        examples=["https://momcare-bucket.s3.amazonaws.com/image.jpg?signature=..."],
    )
    link_expiry_at: datetime | None = Field(None, description="When the link expires", examples=["2024-01-15T18:00:00Z"])

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "link": "https://momcare-bucket.s3.amazonaws.com/exercise-demo.jpg?signature=abc123",
                "link_expiry_at": "2024-01-15T18:00:00Z",
            }
        },
    )


async def _search_food(request: Request, food_name: str, limit: int = 10) -> AsyncIterator[str]:
    async for food in data_handler.get_foods(
        food_name,
        limit=limit,
        fetch_food_image_uri=genai_handler.fetch_food_image_uri,
    ):
        if food["image_uri"] is None or food["image_uri"] == "":
            food["image_uri"] = await pixelbay_image_fetcher.search_image(food_name=food["name"])

        yield json.dumps(food) + "\n"


async def _search_food_name(request: Request, food_name: str, limit: int = 10) -> AsyncIterator[str]:
    async for food in data_handler.get_foods(
        food_name,
        limit=limit,
        fetch_food_image_uri=genai_handler.fetch_food_image_uri,
    ):
        yield json.dumps(food) + "\n"


@router.get("/search", response_class=StreamingResponse)
async def search_food(request: Request, food_name: str, limit: int = 1):
    """
    Search for food items with detailed nutritional information.

    Searches the food database for items matching the query and returns
    comprehensive nutritional data including calories, vitamins, and allergen information.
    """
    foods = _search_food(request, food_name=food_name, limit=limit)
    return StreamingResponse(foods, media_type="application/json")


@router.get("/search/food-name", response_class=StreamingResponse)
async def search_food_name(request: Request, food_name: str, limit: int = 10):
    """
    Search for food items by name without image processing.

    Fast search for food names and basic nutritional information without
    generating or retrieving food images.
    """
    foods = _search_food_name(request, food_name=food_name, limit=limit)
    return StreamingResponse(foods, media_type="application/json")


@router.get("/search/food-name/{food_name}/image")
async def search_food_name_image(request: Request, food_name: str, limit: int = 10):
    """
    Get image URL for a specific food item.

    Retrieves or generates appropriate food images for meal planning
    and nutrition tracking visualization.
    """
    return await pixelbay_image_fetcher.search_image(food_name=food_name)


@router.get("/search/symptoms", response_model=list[Symptom])
async def search_symptoms(request: Request, query: str = "", limit: int | None = None):
    """
    Search for pregnancy and postpartum symptoms information.

    Provides information about common symptoms during pregnancy and postpartum
    period with guidance and recommendations.
    """
    return finder.search_symptoms(query=query, limit=limit)


@router.get("/trimester-data", response_model=TrimesterData | None)
async def search_trimester_data(request: Request, trimester: int):
    """
    Get detailed information about pregnancy trimesters.

    Provides insights into fetal development, maternal health tips, and
    important milestones for each trimester of pregnancy.
    """
    if trimester < 1 or trimester > 3:
        raise HTTPException(status_code=400, detail="Trimester must be between 1 and 3")

    return finder.search_trimester(week_number=trimester * 13)  # Assuming each trimester is roughly 13 weeks


@router.get("/s3/file/{path:path}")
async def get_file(path: str, song: bool = False):
    """
    Get secure access link to a file stored in S3.

    Generates pre-signed URLs for secure access to images, videos, and other media files
    used in the application. Links have time-limited access for security.
    """
    if not path:
        raise HTTPException(status_code=404, detail="File not found")

    link = await s3_client.get_presigned_url(path)

    if not any(path.endswith(ext) for ext in VALID_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Invalid file type")

    if link is None:
        raise HTTPException(status_code=502, detail="Unable to generate link")

    if not song:
        return S3Response(link=link, link_expiry_at=datetime.now(timezone.utc) + timedelta(hours=1))

    song_data = await data_handler.get_song(song_name_or_path=path)
    if song_data is None:
        raise HTTPException(status_code=404, detail="Song not found")

    song_data["uri"] = link
    return song_data


@router.get("/s3/files/{path:path}", response_model=list[str])
async def get_files(path: str):
    """
    List files in a specific S3 directory.

    Browse available media files in categories like exercise images,
    meal photos, or educational content.
    """
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    directories = await s3_client.list_files(prefix=path)

    return directories


@router.get("/s3/directories/{path:path}", response_model=list[str])
async def get_directories(path: str):
    """
    List subdirectories within an S3 path.

    Browse media content organization and discover available content categories.
    """
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    directories = await s3_client.list_folder(prefix=path)

    return directories


@router.get("/quotes/{mood}")
async def get_quote(mood: str):
    """
    Get inspirational quotes based on current mood.

    Provides supportive and encouraging quotes tailored to different emotional states
    during pregnancy and postpartum recovery.
    """
    mood = mood.lower()
    mapper = {
        "happy": HAPPY_QUOTES,
        "sad": SAD_QUOTES,
        "angry": ANGRY_QUOTES,
        "stressed": STRESSED_QUOTES,
    }

    return random.choice(mapper[mood])
