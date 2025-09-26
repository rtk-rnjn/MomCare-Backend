from __future__ import annotations

import random
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from src.app import app, cache_handler, genai_handler, token_handler
from src.models import Exercise, MyPlan, Song, SongMetadata
from src.utils import S3, Finder, PixabayImageFetcher, Symptom, Token, TrimesterData
from src.utils.google_api_handler import YOGA_SETS, _TempDailyInsight
from static.quotes import ANGRY_QUOTES, HAPPY_QUOTES, SAD_QUOTES, STRESSED_QUOTES

if TYPE_CHECKING:
    from typing_extensions import AsyncIterator

security = HTTPBearer()
s3_client = S3(cache_handler=cache_handler)
image_generator_handler = PixabayImageFetcher(cache_handler=cache_handler)
finder = Finder(cache_handler)

ydl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
    "forceurl": True,
}


def get_user_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = token_handler.decode_token(credentials.credentials)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    return token


router = APIRouter(prefix="/content", tags=["Content Management"])
VALID_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]
VALID_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mp3"]
VALID_INPUTS = VALID_IMAGE_EXTENSIONS + VALID_VIDEO_EXTENSIONS


class S3Response(BaseModel):
    """
    Response containing S3 file access information.

    Provides secure links to file content with expiry information for temporary access.
    """

    link: str = Field(
        ..., description="Pre-signed URL for file access", examples=["https://momcare-bucket.s3.amazonaws.com/image.jpg?signature=..."]
    )
    link_expiry_at: Optional[datetime] = Field(None, description="When the link expires", examples=["2024-01-15T18:00:00Z"])

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
    async for food in cache_handler.get_foods(food_name=food_name, limit=limit):
        if food.image_uri is None or food.image_uri == "":
            food.image_uri = await image_generator_handler.search_image(food_name=food.name)

        yield food.model_dump_json() + "\n"


async def _search_food_name(request: Request, food_name: str, limit: int = 10) -> AsyncIterator[str]:
    async for food in cache_handler.get_foods(food_name=food_name, limit=limit):
        yield food.model_dump_json() + "\n"


@router.get("/plan", response_model=MyPlan)
async def get_plan(request: Request, token: Token = Depends(get_user_token)) -> Optional[MyPlan]:
    """
    Generate AI-powered personalized nutrition plan for the user.

    Creates a comprehensive meal plan based on the user's medical data, dietary preferences,
    pregnancy stage, and nutritional requirements. Uses AI to recommend appropriate foods
    for maternal wellness.
    """
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_plan(user)


@router.get("/exercises", response_model=List[Exercise])
async def get_exercises(token: Token = Depends(get_user_token)):
    """
    Get personalized exercise recommendations for maternal fitness.

    Provides exercise routines tailored to the user's pregnancy stage, fitness level,
    and health conditions. Includes safe prenatal and postpartum exercises.
    """
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = await genai_handler.get_exercises(user)
    yoga_sets = data.yoga_sets if data else []
    if not yoga_sets:
        return []

    sendable = []
    for yoga_set in yoga_sets:
        yoga = list(filter(lambda x: x["name"] == yoga_set.name, YOGA_SETS))
        if yoga:
            image_uri = await s3_client.get_presigned_url(f"ExerciseImages/{yoga[0]['image_uri']}")
        else:
            image_uri = None

        exercise = Exercise(
            name=yoga_set.name,
            image_uri=image_uri,
            description=yoga_set.description,
            duration=None,
            level=yoga_set.level,
            targeted_body_parts=yoga_set.targeted_body_parts,
            week=yoga_set.week,
            tags=yoga_set.tags,
        )
        sendable.append(exercise)

    return sendable


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
    return await image_generator_handler.search_image(food_name=food_name)


@router.get("/search/symptoms", response_model=List[Symptom])
async def search_symptoms(request: Request, query: str = "", limit: int | None = None):
    """
    Search for pregnancy and postpartum symptoms information.

    Provides information about common symptoms during pregnancy and postpartum
    period with guidance and recommendations.
    """
    return finder.search_symptoms(query=query, limit=limit)


@router.get("/trimester-data", response_model=Optional[TrimesterData])
async def search_trimester_data(request: Request, trimester: int):
    """
    Get detailed information about pregnancy trimesters.

    Provides insights into fetal development, maternal health tips, and
    important milestones for each trimester of pregnancy.
    """
    if trimester < 1 or trimester > 3:
        raise HTTPException(status_code=400, detail="Trimester must be between 1 and 3")

    return finder.search_trimester(week_number=trimester * 13)  # Assuming each trimester is roughly 13 weeks


@router.get("/tips", response_model=Optional[_TempDailyInsight])
async def get_tips(token: Token = Depends(get_user_token)):
    """
    Get personalized wellness tips and recommendations.

    AI-generated tips based on user's current pregnancy stage, health data,
    and preferences. Includes nutrition advice, exercise suggestions, and wellness guidance.
    """
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_tips(user)


@router.get("/s3/file/{path:path}", response_model=S3Response)
async def get_file(path: str):
    """
    Get secure access link to a file stored in S3.

    Generates pre-signed URLs for secure access to images, videos, and other media files
    used in the application. Links have time-limited access for security.
    """
    if not path:
        raise HTTPException(status_code=404, detail="File not found")

    link = await s3_client.get_presigned_url(path)

    if not any(path.endswith(ext) for ext in VALID_INPUTS):
        raise HTTPException(status_code=400, detail="Invalid file type")

    if link is None:
        raise HTTPException(status_code=502, detail="Unable to generate link")

    return S3Response(
        link=link,
        link_expiry_at=await cache_handler.get_key_expiry(key=f"file:{path}"),
    )


@router.get("/s3/files/{path:path}", response_model=List[str])
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


@router.get("/s3/directories/{path:path}", response_model=List[str])
async def get_directories(path: str):
    """
    List subdirectories within an S3 path.

    Browse media content organization and discover available content categories.
    """
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    directories = await s3_client.list_folder(prefix=path)

    return directories


@router.get("/s3/song/{path:path}", response_model=Song)
async def get_song(path: str):
    """
    Get access to wellness audio content with metadata.

    Provides secure access to meditation tracks, relaxing music, and wellness audio
    designed for maternal mental health support.
    """
    if not path.endswith(tuple(VALID_VIDEO_EXTENSIONS)):
        raise HTTPException(status_code=400, detail="Invalid file type")

    link = await s3_client.get_presigned_url(path)

    if link is None:
        raise HTTPException(status_code=502, detail="Unable to generate link")

    metadata_data = await cache_handler.get_song_metadata(key=path)

    if metadata_data is not None:
        metadata = SongMetadata(
            title=metadata_data.get("title"),
            artist=metadata_data.get("artist"),
            duration=metadata_data.get("duration"),
        )
    else:
        metadata = None

    return Song(
        uri=link,
        metadata=metadata,
        image_uri=None,
    )


@router.get("/quotes/{mood}", response_model=str)
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


app.include_router(router)
