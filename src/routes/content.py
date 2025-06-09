from __future__ import annotations

import random
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict
from yt_dlp import YoutubeDL

from src.app import app, cache_handler, genai_handler, token_handler
from src.models import Exercise, MyPlan, Song, SongMetadata
from src.utils import S3, ImageGeneratorHandler, Token
from static.quotes import ANGRY_QUOTES, HAPPY_QUOTES, SAD_QUOTES, STRESSED_QUOTES

if TYPE_CHECKING:
    from typing_extensions import AsyncIterator

security = HTTPBearer()
s3_client = S3(cache_handler=cache_handler)
image_generator_handler = ImageGeneratorHandler(cache_handler=cache_handler)

ydl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "skip_download": True,
    "forceurl": True,
}


def get_user_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    return token_handler.decode_token(credentials.credentials)


router = APIRouter(prefix="/content", tags=["Content"])
VALID_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]
VALID_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mp3"]
VALID_INPUTS = VALID_IMAGE_EXTENSIONS + VALID_VIDEO_EXTENSIONS


class S3Response(BaseModel):
    link: str
    link_expiry_at: Optional[datetime]

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")},
    )


async def _search_food(request: Request, food_name: str, limit: int = 10) -> AsyncIterator[str]:
    async for food in cache_handler.get_foods(food_name=food_name, limit=limit):
        if food.image_uri is None or food.image_uri == "":
            food.image_uri = await image_generator_handler.search_image(food_name=food.name)

        yield food.model_dump_json() + "\n"


@router.get("/plan")
async def get_plan(request: Request, token: Token = Depends(get_user_token)) -> Optional[MyPlan]:
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_plan(user)


@router.get("/exercises")
async def get_exercises(token: Token = Depends(get_user_token)):
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
        exercise = Exercise(
            name=yoga_set.name,
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
    foods = _search_food(request, food_name=food_name, limit=limit)
    return StreamingResponse(foods, media_type="application/json")


@router.get("/tips")
async def get_tips(token: Token = Depends(get_user_token)):
    user_id = token.sub

    user = await cache_handler.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return await genai_handler.generate_tips(user)


@router.get("/s3/file/{path:path}")
async def get_file(path: str):
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
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    directories = await s3_client.list_files(prefix=path)

    return directories


@router.get("/s3/directories/{path:path}")
async def get_directories(path: str):
    if not path:
        raise HTTPException(status_code=404, detail="Path not found")

    directories = await s3_client.list_folder(prefix=path)

    return directories


@router.get("/s3/song/{path:path}")
async def get_song(path: str):
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
    mood = mood.lower()
    mapper = {"happy": HAPPY_QUOTES, "sad": SAD_QUOTES, "angry": ANGRY_QUOTES, "stressed": STRESSED_QUOTES}

    return random.choice(mapper[mood])


@router.get("/youtube")
async def get_youtube_video(request: Request, video_link: str):
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
