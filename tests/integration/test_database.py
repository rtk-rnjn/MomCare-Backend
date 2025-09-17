"""
Integration tests for database operations.
"""
import pytest
import os
from pymongo.asynchronous.mongo_client import AsyncMongoClient

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestDatabaseIntegration:
    """Test cases for MongoDB integration."""
    
    @pytest.fixture
    async def real_mongo_client(self):
        """Create real MongoDB client for integration tests."""
        uri = os.getenv("MONGODB_URI")
        if not uri:
            pytest.skip("MONGODB_URI not set - skipping integration test")
        
        client = AsyncMongoClient(uri)
        yield client
        await client.close()
    
    async def test_mongodb_connection(self, real_mongo_client):
        """Test MongoDB connection and basic operations."""
        # Test connection
        server_info = await real_mongo_client.server_info()
        assert "version" in server_info
        
        # Test database access
        db = real_mongo_client["MomCare_Test"]
        collection = db["test_collection"]
        
        # Test insert
        test_doc = {"test": "data", "integration": True}
        result = await collection.insert_one(test_doc)
        assert result.inserted_id is not None
        
        # Test find
        found_doc = await collection.find_one({"_id": result.inserted_id})
        assert found_doc["test"] == "data"
        assert found_doc["integration"] is True
        
        # Test delete (cleanup)
        delete_result = await collection.delete_one({"_id": result.inserted_id})
        assert delete_result.deleted_count == 1
    
    async def test_user_collection_operations(self, real_mongo_client):
        """Test user collection operations."""
        db = real_mongo_client["MomCare_Test"]
        users = db["users"]
        
        # Test user insertion
        user_data = {
            "id": "integration_test_user",
            "first_name": "Integration",
            "last_name": "Test",
            "email_address": "integration@test.com",
            "password": "hashed_password",
            "is_verified": True
        }
        
        result = await users.insert_one(user_data)
        assert result.inserted_id is not None
        
        # Test user retrieval
        found_user = await users.find_one({"id": "integration_test_user"})
        assert found_user["first_name"] == "Integration"
        assert found_user["email_address"] == "integration@test.com"
        
        # Test user update
        update_result = await users.update_one(
            {"id": "integration_test_user"},
            {"$set": {"first_name": "Updated"}}
        )
        assert update_result.modified_count == 1
        
        # Verify update
        updated_user = await users.find_one({"id": "integration_test_user"})
        assert updated_user["first_name"] == "Updated"
        
        # Cleanup
        await users.delete_one({"id": "integration_test_user"})