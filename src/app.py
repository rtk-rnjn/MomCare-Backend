from __future__ import annotations

import os
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from src.utils import CacheHandler, GoogleAPIHandler

load_dotenv()

URI = os.getenv("MONGODB_URI")

if URI is None:
    raise ValueError("MONGODB_URI is not set")

mongo_client = AsyncIOMotorClient(URI, document_class=dict[str, Any])
database = mongo_client["MomCare"]
redis_client = Redis()

cache_handler = CacheHandler(
    mongo_client=mongo_client,
    redis_client=redis_client,
)

genai_handler = GoogleAPIHandler(cache_handler=cache_handler)

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
    on_startup=cache_handler.on_startup(),
    on_shutdown=cache_handler.on_shutdown(),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],
)

scheduler = AsyncIOScheduler()
scheduler.add_job(CacheHandler.background_worker(genai_handler), "cron", minute="*")
scheduler.start()

from .routes import *  # noqa: E402, F401, F403
