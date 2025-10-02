from __future__ import annotations

import os
from typing import TYPE_CHECKING

import aiohttp
from dotenv import load_dotenv
from pydantic import BaseModel
from yarl import URL

if TYPE_CHECKING:
    from src.utils.cache_handler import CacheHandler


class PixelRootResponse(BaseModel):
    page: int
    photos: list[PixelPhotoResponse]


class PixelPhotoResponse(BaseModel):
    url: str
    src: PixelPhotoSrcResponse


class PixelPhotoSrcResponse(BaseModel):
    original: str


_ = load_dotenv(verbose=True)

BASE_URL = URL("https://api.pexels.com/v1")


class PixabayImageFetcher:
    def __init__(self, cache_handler: CacheHandler | None = None):
        if cache_handler is None:
            from src.utils.cache_handler import CacheHandler

            self.cache_handler: CacheHandler = CacheHandler()
        else:
            self.cache_handler = cache_handler

        self.api_key: str = os.environ["PIXEL_API_KEY"]
        self.api_url: URL = BASE_URL / "search"

        self.headers: dict[str, str] = {"Authorization": f"{self.api_key}"}

        self.session: aiohttp.ClientSession | None = None

    async def _search_image(self, query: str) -> PixelRootResponse | None:
        if self.session is None:
            self.session = aiohttp.ClientSession(headers=self.headers)

        async with self.session.get(self.api_url, params={"query": query}) as response:
            if response.status == 200:
                data = await response.json()

                return PixelRootResponse(**data)

    async def search_image(self, food_name: str) -> str | None:
        link = await self.cache_handler.get_food_image(food_name=food_name)
        if link:
            return link

        try:
            root_response = await self._search_image(f"{food_name}")
        except aiohttp.ClientError:
            return None

        if root_response is None:
            return None

        if len(root_response.photos) >= 1:
            link = root_response.photos[0].src.original

            await self.cache_handler.set_food_image(food_name=food_name, image_link=link)
            return link
