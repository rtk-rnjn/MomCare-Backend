from __future__ import annotations

import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from yt_dlp import YoutubeDL

from src.app import app, cache_handler, genai_handler, token_handler
from src.models import Exercise, MyPlan, Song, SongMetadata
from src.utils import S3, Finder, ImageGeneratorHandler, Token
from src.utils.google_api_handler import YOGA_SETS
from static.quotes import ANGRY_QUOTES, HAPPY_QUOTES, SAD_QUOTES, STRESSED_QUOTES

if TYPE_CHECKING:
    from typing_extensions import AsyncIterator

security = HTTPBearer()
s3_client = S3(cache_handler=cache_handler)
image_generator_handler = ImageGeneratorHandler(cache_handler=cache_handler)
finder = Finder(cache_handler)

ydl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
    "forceurl": True,
}


def get_user_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Extract and validate JWT token from Authorization header.
    
    Args:
        request: HTTP request object
        credentials: HTTP Bearer token from Authorization header
        
    Returns:
        Token: Decoded token information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
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
    link: str = Field(..., description="Pre-signed URL for file access", examples=["https://momcare-bucket.s3.amazonaws.com/image.jpg?signature=..."])
    link_expiry_at: Optional[datetime] = Field(None, description="When the link expires", examples=["2024-01-15T18:00:00Z"])

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
        json_schema_extra={
            "example": {
                "link": "https://momcare-bucket.s3.amazonaws.com/exercise-demo.jpg?signature=abc123",
                "link_expiry_at": "2024-01-15T18:00:00Z"
            }
        }
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
    
    Args:
        request: HTTP request object
        token: Authenticated user token
        
    Returns:
        MyPlan: Personalized daily nutrition plan with meals and snacks
        
    Raises:
        HTTPException: If user not found (404)
        
    Example:
        Get daily meal plan with breakfast, lunch, dinner, and snacks tailored
        to pregnancy nutritional needs and dietary restrictions.
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
    
    Args:
        token: Authenticated user token
        
    Returns:
        List[Exercise]: List of recommended exercises with instructions and media
        
    Raises:
        HTTPException: If user not found (404)
        
    Example:
        Returns exercises like prenatal yoga, walking routines, and pelvic floor
        strengthening appropriate for current pregnancy week.
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
            level=yoga_set.level,
            targeted_body_parts=yoga_set.targeted_body_parts,
            week=yoga_set.week,
            tags=yoga_set.tags,
        )
        sendable.append(exercise)

    return sendable


@router.get("/search")
async def search_food(request: Request, food_name: str, limit: int = 1):
    """
    Search for food items with detailed nutritional information.
    
    Searches the food database for items matching the query and returns
    comprehensive nutritional data including calories, vitamins, and allergen information.
    
    Args:
        request: HTTP request object
        food_name: Name of food item to search for
        limit: Maximum number of results to return (default: 1)
        
    Returns:
        StreamingResponse: JSON stream of food items with nutritional data
        
    Example:
        Search for "salmon" to get nutritional information, omega-3 content,
        and preparation suggestions for pregnancy-safe consumption.
    """
    foods = _search_food(request, food_name=food_name, limit=limit)
    return StreamingResponse(foods, media_type="application/json")


@router.get("/search/food-name")
async def search_food_name(request: Request, food_name: str, limit: int = 10):
    """
    Search for food items by name without image processing.
    
    Fast search for food names and basic nutritional information without
    generating or retrieving food images.
    
    Args:
        request: HTTP request object
        food_name: Name of food item to search for
        limit: Maximum number of results to return (default: 10)
        
    Returns:
        StreamingResponse: JSON stream of food items with basic information
        
    Example:
        Quick search for "apple" to get multiple apple varieties and their
        basic nutritional profiles.
    """
    foods = _search_food_name(request, food_name=food_name, limit=limit)
    return StreamingResponse(foods, media_type="application/json")


@router.get("/search/food-name/{food_name}/image")
async def search_food_name_image(request: Request, food_name: str, limit: int = 10):
    """
    Get image URL for a specific food item.
    
    Retrieves or generates appropriate food images for meal planning
    and nutrition tracking visualization.
    
    Args:
        request: HTTP request object
        food_name: Name of food item to get image for
        limit: Number of images to consider (default: 10)
        
    Returns:
        str: URL to food item image
        
    Example:
        Get visual representation of "grilled chicken" for meal planning interface.
    """
    return await image_generator_handler.search_image(food_name=food_name)


@router.get("/search/symptoms")
async def search_symptoms(request: Request, query: str = "", limit: int | None = None):
    """
    Search for pregnancy and postpartum symptoms information.
    
    Provides information about common symptoms during pregnancy and postpartum
    period with guidance and recommendations.
    
    Args:
        request: HTTP request object
        query: Symptom description to search for
        limit: Maximum number of results (optional)
        
    Returns:
        List: Symptom information and recommendations
        
    Example:
        Search for "nausea" to get information about morning sickness
        and management strategies.
    """
    return finder.search_symptoms(query=query, limit=limit)


@router.get("/tips")
async def get_tips(token: Token = Depends(get_user_token)):
    """
    Get personalized wellness tips and recommendations.
    
    AI-generated tips based on user's current pregnancy stage, health data,
    and preferences. Includes nutrition advice, exercise suggestions, and wellness guidance.
    
    Args:
        token: Authenticated user token
        
    Returns:
        List: Personalized wellness tips and recommendations
        
    Raises:
        HTTPException: If user not found (404)
        
    Example:
        Get weekly tips like "Focus on iron-rich foods this week" or
        "Try gentle prenatal yoga for back pain relief".
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
    
    Args:
        path: S3 file path (e.g., "ExerciseImages/yoga-pose.jpg")
        
    Returns:
        S3Response: Secure link and expiry information
        
    Raises:
        HTTPException: 
            - If file path is invalid (404)
            - If file type is not supported (400) 
            - If unable to generate link (502)
            
    Example:
        Get access to exercise demonstration video or meal planning images.
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


@router.get("/s3/files/{path:path}")
async def get_files(path: str):
    """
    List files in a specific S3 directory.
    
    Browse available media files in categories like exercise images,
    meal photos, or educational content.
    
    Args:
        path: S3 directory path to list files from
        
    Returns:
        List: Available files in the specified directory
        
    Raises:
        HTTPException: If directory path not found (404)
        
    Example:
        List all available exercise demonstration videos or nutrition guides.
    """
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    directories = await s3_client.list_files(prefix=path)

    return directories


@router.get("/s3/directories/{path:path}")
async def get_directories(path: str):
    """
    List subdirectories within an S3 path.
    
    Browse media content organization and discover available content categories.
    
    Args:
        path: S3 directory path to explore
        
    Returns:
        List: Available subdirectories
        
    Raises:
        HTTPException: If directory path not found (404)
        
    Example:
        Explore content categories like "ExerciseVideos", "NutritionGuides", etc.
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
    
    Args:
        path: S3 audio file path
        
    Returns:
        Song: Audio access link with metadata (title, artist, duration)
        
    Raises:
        HTTPException:
            - If file type is invalid (400)
            - If unable to generate link (502)
            
    Example:
        Access prenatal meditation tracks or soothing music for relaxation.
    """
    if not path.endswith(tuple(VALID_VIDEO_EXTENSIONS)):
        raise HTTPException(status_code=400, detail="Invalid file type")

    link = await s3_client.get_presigned_url(path)

    if link is None:
        raise HTTPException(status_code=502, detail="Unable to generate link")

    metadata = await cache_handler.get_song_metadata(key=path)

    return Song(
        uri=link,
        metadata=SongMetadata(**metadata) if metadata else None,
    )


@router.get("/quotes/{mood}")
async def get_quote(mood: str):
    """
    Get inspirational quotes based on current mood.
    
    Provides supportive and encouraging quotes tailored to different emotional states
    during pregnancy and postpartum recovery.
    
    Args:
        mood: Current mood state ("happy", "sad", "angry", "stressed")
        
    Returns:
        str: Appropriate inspirational quote
        
    Example:
        Get uplifting quotes for "stressed" mood or celebratory quotes for "happy" mood.
    """
    mood = mood.lower()
    mapper = {
        "happy": HAPPY_QUOTES,
        "sad": SAD_QUOTES,
        "angry": ANGRY_QUOTES,
        "stressed": STRESSED_QUOTES,
    }

    return random.choice(mapper[mood])


@router.get("/youtube")
async def get_youtube_video(request: Request, video_link: str):
    """
    Extract YouTube video information for wellness content.
    
    Processes YouTube links to extract video metadata and direct access URLs
    for educational content about pregnancy, exercise, and nutrition.
    
    Args:
        request: HTTP request object
        video_link: YouTube video URL
        
    Returns:
        dict: Video information including title, duration, and access URL
        
    Raises:
        HTTPException:
            - If video link is missing (400)
            - If video not found (404)
            
    Example:
        Process prenatal yoga tutorial videos or nutrition education content.
        
    Note:
        This endpoint processes YouTube content for educational purposes only.
    """
    # Sorry Youtube
    if not video_link:
        raise HTTPException(status_code=400, detail="Video link is required")

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_link, download=False)
        if not info:
            raise HTTPException(status_code=404, detail="Video not found")

        video_url = info["url"]
        title = info.get("title", "Unknown Title")
        duration = info.get("duration", 0)

    return {
        "video_url": video_url,
        "title": title,
        "duration": duration,
    }


app.include_router(router)
