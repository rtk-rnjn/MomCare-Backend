from __future__ import annotations

import os

import aiohttp
from dotenv import load_dotenv
from pydantic import BaseModel
from yarl import URL


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
    def __init__(self):

        self.api_key: str = os.environ["PIXEL_API_KEY"]
        self.api_url: URL = BASE_URL / "search"

        self.headers: dict[str, str] = {"Authorization": f"{self.api_key}"}

        self.session: aiohttp.ClientSession | None = None

    async def _search_image_from_pixel(self, query: str) -> PixelRootResponse | None:
        if self.session is None:
            self.session = aiohttp.ClientSession(headers=self.headers)

        async with self.session.get(self.api_url, params={"query": query}) as response:
            if response.status == 200:
                data = await response.json()

                return PixelRootResponse(**data)

    async def search_image(self, food_name: str) -> str | None:
        try:
            root_response = await self._search_image_from_pixel(f"{food_name}")
        except aiohttp.ClientError:
            return None

        if root_response is None:
            return None

        if not root_response.photos:
            return None

        return root_response.photos[0].src.original
