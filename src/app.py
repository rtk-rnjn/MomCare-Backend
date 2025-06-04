from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from src.utils import CacheHandler, GoogleAPIHandler, TokenHandler

load_dotenv()

URI = os.getenv("MONGODB_URI")

if URI is None:
    raise ValueError("MONGODB_URI is not set")

mongo_client = AsyncIOMotorClient(URI, document_class=dict[str, Any])
database = mongo_client["MomCare"]
redis_client = Redis(decode_responses=True)

cache_handler = CacheHandler(
    mongo_client=mongo_client,
    redis_client=redis_client,
)

genai_handler = GoogleAPIHandler(cache_handler=cache_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    genai_handler = GoogleAPIHandler(cache_handler=cache_handler)
    await cache_handler.on_startup(genai_handler)
    yield
    await cache_handler.on_shutdown()


app = FastAPI(
    title="MomCare API Documentation",
    description="API documentation for the MomCare project - a health and fitness application. The API is used to manage users, exercises, and plans.",
    version="0.1",
    contact={
        "name": "Team 05 - Vision",
        "url": "https://github.com/rtk-rnjn/MomCare",
    },
    license_info={
        "name": "Mozilla Public License Version 2.0",
        "url": "https://opensource.org/licenses/MPL-2.0",
    },
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "User-Agent"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],
)

token_handler = TokenHandler(os.environ["JWT_SECRET"])

from .routes import *  # noqa: E402, F401, F403
