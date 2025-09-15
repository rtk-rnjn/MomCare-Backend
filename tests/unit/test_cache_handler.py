"""
Unit tests for cache handler utility.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.unit


class TestCacheHandler:
    """Test cases for CacheHandler class."""
    
    @pytest.mark.asyncio
    async def test_cache_handler_initialization(self, mock_mongo_client, mock_redis_client):
        """Test CacheHandler initialization."""
        from src.utils.cache_handler import CacheHandler
        
        cache_handler = CacheHandler(
            mongo_client=mock_mongo_client,
            redis_client=mock_redis_client
        )
        
        assert cache_handler.mongo_client == mock_mongo_client
        assert cache_handler.redis_client == mock_redis_client
    
    @pytest.mark.asyncio
    async def test_on_startup(self, mock_cache_handler, mock_google_api_handler):
        """Test cache handler startup operations."""
        await mock_cache_handler.on_startup(mock_google_api_handler)
        
        # Verify startup was called
        mock_cache_handler.on_startup.assert_called_once_with(mock_google_api_handler)
    
    @pytest.mark.asyncio
    async def test_on_shutdown(self, mock_cache_handler):
        """Test cache handler shutdown operations."""
        await mock_cache_handler.on_shutdown()
        
        # Verify shutdown was called
        mock_cache_handler.on_shutdown.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_database_operations(self, mock_cache_handler):
        """Test database operations through cache handler."""
        # Test user operations
        user_data = {"id": "user_123", "name": "Test User"}
        
        # Mock insert operation
        mock_cache_handler.users.insert_one = AsyncMock(
            return_value=MagicMock(inserted_id="user_123")
        )
        
        result = await mock_cache_handler.users.insert_one(user_data)
        assert result.inserted_id == "user_123"
        
        # Mock find operation
        mock_cache_handler.users.find_one = AsyncMock(return_value=user_data)
        
        found_user = await mock_cache_handler.users.find_one({"id": "user_123"})
        assert found_user == user_data
    
    @pytest.mark.asyncio
    async def test_redis_operations(self, mock_cache_handler):
        """Test Redis cache operations."""
        key = "test_key"
        value = "test_value"
        
        # Test set operation
        mock_cache_handler.redis_client.set = AsyncMock(return_value=True)
        result = await mock_cache_handler.redis_client.set(key, value)
        assert result is True
        
        # Test get operation
        mock_cache_handler.redis_client.get = AsyncMock(return_value=value)
        cached_value = await mock_cache_handler.redis_client.get(key)
        assert cached_value == value
        
        # Test delete operation
        mock_cache_handler.redis_client.delete = AsyncMock(return_value=1)
        deleted = await mock_cache_handler.redis_client.delete(key)
        assert deleted == 1