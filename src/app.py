from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.middleware.monitoring import MonitoringMiddleware
from src.utils import (
    S3,
    DatabaseMonitor,
    GoogleAPIHandler,
    MonitoringHandler,
    PixabayImageFetcher,
    SystemMonitor,
    TokenHandler,
)

load_dotenv(verbose=True)

MONGO_URI = os.environ["MONGODB_URI"]


pixelbay_image_fetcher = PixabayImageFetcher()
genai_handler = GoogleAPIHandler()
s3_client = S3()
monitoring_handler = MonitoringHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.monitoring_handler = monitoring_handler
    app.state.monitoring_handler.connect("monitoring.db")

    # Initialize database monitor
    from src.routes.utils.data_handler import data_handler, mongo_client

    app.state.database_monitor = DatabaseMonitor(mongo_client=mongo_client, redis_client=data_handler.redis_client)

    # Initialize system monitor
    app.state.system_monitor = SystemMonitor()

    try:
        yield
    finally:
        if hasattr(app.state, "monitoring_handler"):
            app.state.monitoring_handler.shutdown()


with open("version.txt", "r") as vf:
    version = vf.read().strip()

app = FastAPI(
    title="MomCare API",
    version=version,
    contact={
        "name": "Vision",
        "url": "https://github.com/rtk-rnjn/MomCare",
        "email": "ritik0ranjan@gmail.com",
    },
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
            "name": "AI Content",
            "description": "AI-generated content and recommendations for maternal health, including personalized meal plans, exercise routines, and wellness tips.",  # noqa: E501
        },
        {
            "name": "Content Management",
            "description": "Access to media content, including images, videos, and articles related to maternal health and wellness.",
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


app.add_middleware(MonitoringMiddleware)

app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")
app.state.templates = templates

token_handler = TokenHandler(os.environ["JWT_SECRET"])

from .routes import v1_router as v1_router  # noqa: E402

app.include_router(v1_router)
