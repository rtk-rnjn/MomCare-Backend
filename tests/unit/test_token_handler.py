"""
Unit tests for token handler utility.
"""
import pytest
from unittest.mock import patch, MagicMock
import os
from datetime import datetime, timedelta

from src.utils.token_handler import TokenHandler, Token
from src.models.user import User


class TestTokenHandler:
    """Test cases for TokenHandler class."""
    
    def test_token_handler_initialization(self):
        """Test TokenHandler initialization."""
        secret = "test_secret_key"
        handler = TokenHandler(secret)
        assert handler.secret == secret
        assert handler.algorithm == "HS256"
    
    def test_create_access_token(self):
        """Test access token creation."""
        handler = TokenHandler("test_secret")
        
        # Create a mock user
        user_data = {
            "id": "test_user_123",
            "first_name": "Test",
            "last_name": "User",
            "email_address": "test@example.com",
            "password": "password123",
            "is_verified": True,
            "dob": "1990-01-01",
            "height": 165.0,
            "weight": 60.0,
            "goals": ["fitness"],
            "medical_conditions": []
        }
        user = User(**user_data)
        
        token = handler.create_access_token(user)
        
        assert isinstance(token, str)
        assert len(token) > 0
        # Should be a JWT token with 3 parts separated by dots
        assert len(token.split('.')) == 3
    
    def test_validate_token_valid(self):
        """Test token validation with valid token."""
        handler = TokenHandler("test_secret")
        
        # Create a mock user
        user_data = {
            "id": "test_user_123",
            "first_name": "Test",
            "last_name": "User",
            "email_address": "test@example.com",
            "password": "password123",
            "is_verified": True,
            "dob": "1990-01-01",
            "height": 165.0,
            "weight": 60.0,
            "goals": ["fitness"],
            "medical_conditions": []
        }
        user = User(**user_data)
        
        # Create a token and then validate it
        token = handler.create_access_token(user)
        decoded = handler.validate_token(token)
        
        assert decoded is not None
        assert decoded.sub == user.id
        assert decoded.email == user.email_address
        assert decoded.verified == user.is_verified
        assert decoded.name == f"{user.first_name} {user.last_name}"
    
    def test_validate_token_invalid(self):
        """Test token validation with invalid token."""
        handler = TokenHandler("test_secret")
        
        result = handler.validate_token("invalid_token")
        assert result is None
    
    def test_validate_token_wrong_secret(self):
        """Test token validation with wrong secret."""
        handler1 = TokenHandler("secret1")
        handler2 = TokenHandler("secret2")
        
        # Create a mock user
        user_data = {
            "id": "test_user_123",
            "first_name": "Test",
            "last_name": "User",
            "email_address": "test@example.com",
            "password": "password123",
            "is_verified": True,
            "dob": "1990-01-01",
            "height": 165.0,
            "weight": 60.0,
            "goals": ["fitness"],
            "medical_conditions": []
        }
        user = User(**user_data)
        
        token = handler1.create_access_token(user)
        result = handler2.validate_token(token)
        
        assert result is None
    
    def test_decode_token(self):
        """Test decode_token method (alias for validate_token)."""
        handler = TokenHandler("test_secret")
        
        # Create a mock user
        user_data = {
            "id": "test_user_123",
            "first_name": "Test",
            "last_name": "User",
            "email_address": "test@example.com",
            "password": "password123",
            "is_verified": True,
            "dob": "1990-01-01",
            "height": 165.0,
            "weight": 60.0,
            "goals": ["fitness"],
            "medical_conditions": []
        }
        user = User(**user_data)
        
        token = handler.create_access_token(user)
        decoded = handler.decode_token(token)
        
        assert decoded is not None
        assert decoded.sub == user.id
    
    def test_validate_token_unverified_user(self):
        """Test token validation with unverified user."""
        handler = TokenHandler("test_secret")
        
        # Create a mock user that is not verified
        user_data = {
            "id": "test_user_123",
            "first_name": "Test",
            "last_name": "User",
            "email_address": "test@example.com",
            "password": "password123",
            "is_verified": False,  # Not verified
            "dob": "1990-01-01",
            "height": 165.0,
            "weight": 60.0,
            "goals": ["fitness"],
            "medical_conditions": []
        }
        user = User(**user_data)
        
        token = handler.create_access_token(user)
        decoded = handler.validate_token(token)
        
        # Should return None for unverified users
        assert decoded is None


class TestToken:
    """Test cases for Token class."""
    
    def test_token_creation(self):
        """Test Token class creation."""
        token_data = {
            "sub": "user_123",
            "email": "test@example.com",
            "verified": True,
            "name": "Test User",
            "exp": int((datetime.now() + timedelta(hours=1)).timestamp())
        }
        token = Token(**token_data)
        
        assert token.sub == "user_123"
        assert token.email == "test@example.com"
        assert token.verified is True
        assert token.name == "Test User"
    
    def test_token_defaults(self):
        """Test Token class with default values."""
        token_data = {
            "sub": "user_123",
            "email": "test@example.com",
            "verified": True,
            "name": "Test User",
            "exp": int((datetime.now() + timedelta(hours=1)).timestamp())
        }
        token = Token(**token_data)
        
        # iat should be set automatically
        assert hasattr(token, 'iat')
        assert isinstance(token.iat, int)