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

mongo_client = AsyncIOMotorClient(URI, tz_aware=True, document_class=dict[str, Any])
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

    if hasattr(app, "sqlite_handler"):
        app.sqlite_handler.connect("logs.db")  # pyright: ignore[reportAttributeAccessIssue]

    try:
        yield
    finally:
        if hasattr(app, "sqlite_handler"):
            app.sqlite_handler.shutdown()  # pyright: ignore[reportAttributeAccessIssue]

    await cache_handler.on_shutdown()


app = FastAPI(
    title="MomCare API",
    version="1.1.0",
    contact={"name": "Team 05 - Vision", "url": "https://github.com/rtk-rnjn/MomCare", "email": "ritik0ranjan@gmail.com"},
    license_info={
        "name": "GNU General Public License v2.0",
        "url": "https://opensource.org/licenses/GPL-2.0",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    tags_metadata=[
        {
            "name": "Authentication",
            "description": "User registration, login, and profile management operations. Handle user accounts, authentication tokens, and personal information updates.",  # noqa: E501
        },
        {
            "name": "Content Management",
            "description": "Access to nutrition plans, exercise routines, food search, wellness tips, and media content. Core functionality for maternal health and fitness.",  # noqa: E501
        },
        {
            "name": "OTP Authentication",
            "description": "One-time password operations for email verification and account security. Secure account verification workflows.",  # noqa: E501
        },
        {
            "name": "System & Meta",
            "description": "System health checks, API metadata, versioning information, and service status endpoints for monitoring and integration.",  # noqa: E501
        },
    ],
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
