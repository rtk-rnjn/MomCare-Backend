from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis

from src.utils import S3, GoogleAPIHandler, PixabayImageFetcher, TokenHandler

load_dotenv(verbose=True)

URI = os.getenv("MONGODB_URI")

if URI is None:
    raise ValueError("MONGODB_URI is not set")

mongo_client = AsyncIOMotorClient(URI, tz_aware=True, document_class=dict[str, Any])
database = mongo_client["MomCare"]
redis_client = Redis(decode_responses=True)


pixelbay_image_fetcher = PixabayImageFetcher()
genai_handler = GoogleAPIHandler()
s3_client = S3()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if hasattr(app.state, "sqlite_handler"):
        app.state.sqlite_handler.connect("logs.db")

    await redis_client.ping()
    await mongo_client.admin.command("ping")

    try:
        yield
    finally:
        if hasattr(app.state, "sqlite_handler"):
            app.state.sqlite_handler.shutdown()


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
            "name": "Update Management",
            "description": "Operations for updating user medical data, preferences, and account settings. Manage user-specific information and configurations.",  # noqa: E501
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

app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

token_handler = TokenHandler(os.environ["JWT_SECRET"])

from .routes import v1_router as v1_router

app.include_router(v1_router)
