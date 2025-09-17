"""
Pytest configuration and fixtures for MomCare Backend tests.
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator, Generator

# Mock environment variables for unit tests
MOCK_ENV_VARS = {
    "HOST": "localhost",
    "PORT": "8000",
    "AWS_ACCESS_KEY": "mock_aws_access_key",
    "AWS_SECRET_KEY": "mock_aws_secret_key",
    "AWS_REGION": "us-east-1",
    "AWS_BUCKET_NAME": "mock-bucket",
    "EMAIL_ADDRESS": "test@example.com",
    "EMAIL_PASSWORD": "mock_password",
    "GEMINI_API_KEY": "mock_gemini_key",
    "JWT_SECRET": "mock_jwt_secret_for_testing_only",
    "MONGODB_URI": "mongodb://mock_uri",
    "PIXEL_API_KEY": "mock_pixel_key",
    "SEARCH_API_KEY": "mock_search_key",
    "SEARCH_API_CX": "mock_search_cx",
}


@pytest.fixture(scope="session", autouse=True)
def mock_environment() -> Generator[None, None, None]:
    """Mock environment variables for all tests."""
    with patch.dict(os.environ, MOCK_ENV_VARS):
        yield


# Set environment variables at module level to fix import issues
for key, value in MOCK_ENV_VARS.items():
    os.environ.setdefault(key, value)


@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB client."""
    mock_client = MagicMock()
    mock_database = MagicMock()
    mock_collection = MagicMock()
    
    mock_client.__getitem__.return_value = mock_database
    mock_database.__getitem__.return_value = mock_collection
    
    # Configure async methods
    mock_collection.insert_one = AsyncMock()
    mock_collection.find_one = AsyncMock()
    mock_collection.update_one = AsyncMock()
    mock_collection.delete_one = AsyncMock()
    mock_collection.find = MagicMock()
    
    return mock_client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = 1
    mock_redis.exists.return_value = False
    return mock_redis


@pytest.fixture
def mock_cache_handler(mock_mongo_client, mock_redis_client):
    """Mock CacheHandler."""
    with patch("src.utils.CacheHandler") as mock_cache:
        mock_instance = AsyncMock()
        mock_instance.mongo_client = mock_mongo_client
        mock_instance.redis_client = mock_redis_client
        mock_instance.on_startup = AsyncMock()
        mock_instance.on_shutdown = AsyncMock()
        mock_cache.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_google_api_handler():
    """Mock GoogleAPIHandler."""
    with patch("src.utils.GoogleAPIHandler") as mock_handler:
        mock_instance = AsyncMock()
        mock_instance.search_food = AsyncMock(return_value={"results": []})
        mock_instance.generate_content = AsyncMock(return_value="Mock AI response")
        mock_handler.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_token_handler():
    """Mock TokenHandler."""
    with patch("src.utils.TokenHandler") as mock_handler:
        mock_instance = MagicMock()
        mock_instance.encode_token.return_value = "mock_jwt_token"
        mock_instance.decode_token.return_value = {"sub": "mock_user_id"}
        mock_handler.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_email_handler():
    """Mock email sending functionality."""
    with patch("src.utils.email_handler.send_otp_mail") as mock_send:
        mock_send.return_value = AsyncMock()
        yield mock_send


@pytest.fixture
def mock_s3_client():
    """Mock AWS S3 client."""
    with patch("boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_s3.upload_fileobj.return_value = None
        mock_s3.delete_object.return_value = None
        mock_s3.generate_presigned_url.return_value = "https://mock-s3-url.com/file"
        mock_boto.return_value = mock_s3
        yield mock_s3


@pytest.fixture
def mock_fastapi_app():
    """Mock FastAPI app with mocked dependencies."""
    # Mock all the heavy imports before importing the app
    with (
        patch("src.app.AsyncMongoClient"),
        patch("src.app.Redis"),
        patch("src.utils.CacheHandler"),
        patch("src.utils.GoogleAPIHandler"),
        patch("src.utils.TokenHandler"),
        patch.dict(os.environ, MOCK_ENV_VARS),
    ):
        from src.app import app
        return app


@pytest.fixture
def sample_user_data():
    """Sample user data for testing."""
    return {
        "id": "test_user_123",
        "first_name": "Test",
        "last_name": "User",
        "email_address": "test@example.com",
        "password": "test_password123",
        "dob": "1990-01-01",
        "height": 165.0,
        "weight": 60.0,
        "goals": ["fitness", "nutrition"],
        "medical_conditions": []
    }


@pytest.fixture
def sample_auth_request():
    """Sample authentication request data."""
    return {
        "email_address": "test@example.com",
        "password": "test_password123"
    }


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for authentication."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0X3VzZXJfMTIzIiwiZXhwIjoxNjQyNjgwMDAwfQ.mock_signature"


@pytest.fixture
def auth_headers(mock_jwt_token):
    """Authentication headers for API requests."""
    return {"Authorization": f"Bearer {mock_jwt_token}"}