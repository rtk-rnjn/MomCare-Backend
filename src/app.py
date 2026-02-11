from __future__ import annotations

import os

import arrow
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from redis.asyncio import Redis

from src.utils import S3, EmailNormalizer, GoogleAPIHandler, TokenManager

with open("version.txt", "r") as f:
    __version__ = f.read().strip()

app = FastAPI(
    title="MomCare API",
    description="API for MomCare - a personalized health and wellness assistant for pregnant women. Provides endpoints for user authentication, exercise and meal tracking, AI-generated insights, and more.",
    version=__version__,
    summary="MomCare API",
    contact={
        "name": "MomCare Support",
        "email": "ritik0ranjan@gmail.com",
        "url": "https://github.com/rtk-rnjn/MomCare-Backend",
    },
    license_info={
        "name": "GPL-2.0 License",
        "url": "https://www.gnu.org/licenses/old-licenses/gpl-2.0.html",
    },
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
            "name": "AI Content",
            "description": "AI-generated content and recommendations for maternal health, including personalized meal plans, exercise routines, and wellness tips.",  # noqa: E501
        },
        {
            "name": "Content Utils",
            "description": "Access to media content, including images, videos, and articles related to maternal health and wellness.",
        },
        {
            "name": "System & Meta",
            "description": "System health checks, API metadata, versioning information, and service status endpoints for monitoring and integration.",  # noqa: E501
        },
    ],
)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_DB = int(os.getenv("REDIS_DB", 5))

auth_manager = TokenManager()
google_api_handler = GoogleAPIHandler()
s3 = S3()
redis_client = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,
    protocol=3,
)

mongo_client = AsyncMongoClient(MONGODB_URI, tz_aware=True)
email_normalizer = EmailNormalizer()

app.state.auth_manager = auth_manager
app.state.google_api_handler = google_api_handler
app.state.s3 = s3
app.state.redis_client = redis_client
app.state.email_normalizer = email_normalizer
app.state.start_time = arrow.utcnow()

app.state.mongo_client = mongo_client
app.state.mongo_database = mongo_client["MomCare"]

app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")
app.state.templates = templates


from .middleware import *  # noqa: E402, F403
from .routes import api_router, web_router  # noqa: E402

app.include_router(api_router)
app.include_router(web_router)
