from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.app import app, cache_handler, genai_handler
from src.models import MyPlan, Song, SongMetadata
from src.utils import S3, ImageGeneratorHandler, Token, TokenHandler

if TYPE_CHECKING:
    from typing_extensions import AsyncIterator

token_handler = TokenHandler(os.environ["JWT_SECRET"])
security = HTTPBearer()
s3_client = S3(cache_handler=cache_handler)
image_generator_handler = ImageGeneratorHandler(cache_handler=cache_handler)


def get_user_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)):
    return token_handler.decode_token(credentials.credentials)


router = APIRouter(prefix="/content", tags=["Content"])
VALID_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif"]
VALID_VIDEO_EXTENSIONS = [".mp4", ".avi", ".mov", ".mp3"]
VALID_INPUTS = VALID_IMAGE_EXTENSIONS + VALID_VIDEO_EXTENSIONS


class S3Response(BaseModel):
    link: str
    link_expiry_at: Optional[datetime]

    class Config:
        json_encoders = {
            datetime: lambda datetime_object: datetime_object.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


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


app.include_router(router)
