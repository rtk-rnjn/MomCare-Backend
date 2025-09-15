from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from redis.asyncio import Redis

from src.utils import CacheHandler, GoogleAPIHandler, TokenHandler

load_dotenv()

URI = os.getenv("MONGODB_URI")

if URI is None:
    raise ValueError("MONGODB_URI is not set")

mongo_client = AsyncMongoClient(URI, document_class=dict[str, Any])
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

    yield
    if hasattr(app, "sqlite_handler"):
        app.sqlite_handler.shutdown()  # pyright: ignore[reportAttributeAccessIssue]

    await cache_handler.on_shutdown()


app = FastAPI(
    title="MomCare API",
    description="""
    ## MomCare API Documentation

    Welcome to the **MomCare API** - a comprehensive health and fitness application backend designed specifically for maternal wellness and care.

    ### Key Features:
    * **User Management**: Complete user registration, authentication, and profile management
    * **Health Tracking**: Medical data tracking, mood monitoring, and history management  
    * **Nutrition Planning**: AI-powered meal planning with detailed nutritional information
    * **Exercise Management**: Personalized exercise routines with progress tracking
    * **Content Discovery**: Food search, exercise recommendations, and wellness tips
    * **Media Management**: Secure file storage and multimedia content handling

    ### Authentication:
    Most endpoints require JWT authentication. Include your access token in the `Authorization` header:
    ```
    Authorization: Bearer <your-access-token>
    ```

    ### Getting Started:
    1. Register a new user account at `/auth/register`
    2. Login to receive an access token at `/auth/login`  
    3. Use the token to access protected endpoints

    ### Support:
    For questions or issues, please visit our [GitHub repository](https://github.com/rtk-rnjn/MomCare).
    """,
    version="1.0.0",
    contact={
        "name": "Team 05 - Vision",
        "url": "https://github.com/rtk-rnjn/MomCare",
        "email": "support@momcare.app"
    },
    license_info={
        "name": "Mozilla Public License Version 2.0",
        "url": "https://opensource.org/licenses/MPL-2.0",
    },
    terms_of_service="https://github.com/rtk-rnjn/MomCare/blob/main/TERMS.md",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    tags_metadata=[
        {
            "name": "Authentication",
            "description": "User registration, login, and profile management operations. Handle user accounts, authentication tokens, and personal information updates."
        },
        {
            "name": "Content Management", 
            "description": "Access to nutrition plans, exercise routines, food search, wellness tips, and media content. Core functionality for maternal health and fitness."
        },
        {
            "name": "OTP Authentication",
            "description": "One-time password operations for email verification and account security. Secure account verification workflows."
        },
        {
            "name": "System & Meta",
            "description": "System health checks, API metadata, versioning information, and service status endpoints for monitoring and integration."
        }
    ]
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
