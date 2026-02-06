from __future__ import annotations

import os

import pymongo
import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.utils import S3, GoogleAPIHandler, TokenManager

app = FastAPI()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_DB = int(os.getenv("REDIS_DB", 5))

auth_manager = TokenManager()
google_api_handler = GoogleAPIHandler()
s3 = S3()
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True,
    protocol=3,
)

mongo_client = pymongo.MongoClient(MONGODB_URI)

app.state.auth_manager = auth_manager
app.state.google_api_handler = google_api_handler
app.state.s3 = s3
app.state.redis_client = redis_client

app.state.mongo_client = mongo_client
app.state.mongo_database = mongo_client["MomCare"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")
app.state.templates = templates


from .routes import api_router  # noqa: E402

app.include_router(api_router)
