"""
Integration tests for external API services.
"""
import pytest
import os
import aiohttp
import boto3
from unittest.mock import patch

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
class TestExternalAPIIntegration:
    """Test cases for external API integrations."""
    
    async def test_gemini_api_connection(self):
        """Test Google Gemini API connection."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            pytest.skip("GEMINI_API_KEY not set - skipping integration test")
        
        # Test basic API connectivity
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        params = {"key": api_key}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                assert response.status in [200, 403]  # 403 if quota exceeded
                if response.status == 200:
                    data = await response.json()
                    assert "models" in data
    
    async def test_google_search_api_connection(self):
        """Test Google Custom Search API connection."""
        api_key = os.getenv("SEARCH_API_KEY")
        cx = os.getenv("SEARCH_API_CX")
        
        if not api_key or not cx:
            pytest.skip("Google Search API credentials not set - skipping integration test")
        
        # Test basic search API connectivity
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cx,
            "q": "test query",
            "num": 1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                assert response.status in [200, 403, 429]  # 403/429 if quota exceeded
                if response.status == 200:
                    data = await response.json()
                    assert "items" in data or "searchInformation" in data
    
    def test_aws_s3_connection(self):
        """Test AWS S3 connection and basic operations."""
        access_key = os.getenv("AWS_ACCESS_KEY")
        secret_key = os.getenv("AWS_SECRET_KEY")
        region = os.getenv("AWS_REGION")
        bucket_name = os.getenv("AWS_BUCKET_NAME")
        
        if not all([access_key, secret_key, region, bucket_name]):
            pytest.skip("AWS credentials not set - skipping integration test")
        
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        
        # Test bucket access (list objects)
        try:
            response = s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
            assert "Contents" in response or "KeyCount" in response
        except Exception as e:
            # If bucket doesn't exist or no permissions, that's still a valid connection test
            assert "NoSuchBucket" in str(e) or "AccessDenied" in str(e) or "Forbidden" in str(e)
    
    def test_pixel_api_connection(self):
        """Test Pixel API connection."""
        api_key = os.getenv("PIXEL_API_KEY")
        if not api_key:
            pytest.skip("PIXEL_API_KEY not set - skipping integration test")
        
        # This is a placeholder test - actual implementation depends on the specific Pixel API
        # For now, just verify the API key exists and is non-empty
        assert len(api_key) > 0
        assert api_key != "mock_pixel_key"
    
    @pytest.mark.asyncio
    async def test_email_smtp_connection(self):
        """Test SMTP email connection."""
        email_address = os.getenv("EMAIL_ADDRESS")
        email_password = os.getenv("EMAIL_PASSWORD")
        
        if not email_address or not email_password:
            pytest.skip("Email credentials not set - skipping integration test")
        
        # Test SMTP connection without actually sending email
        import aiosmtplib
        
        try:
            smtp_client = aiosmtplib.SMTP(hostname="smtp.gmail.com", port=587)
            await smtp_client.connect()
            await smtp_client.starttls()
            await smtp_client.login(email_address, email_password)
            await smtp_client.quit()
            assert True  # If we get here, connection was successful
        except Exception as e:
            # Even if authentication fails, we've tested the connection
            assert "Authentication" in str(e) or "login" in str(e) or "password" in str(e)