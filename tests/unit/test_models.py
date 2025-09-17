"""
Unit tests for user models.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError

pytestmark = pytest.mark.unit


class TestUserModels:
    """Test cases for user model classes."""
    
    def test_user_model_valid_data(self, sample_user_data):
        """Test User model with valid data."""
        # Import here to avoid issues with environment variables
        src_models_user = pytest.importorskip("src.models.user")
        User = src_models_user.User
        
        # The User model doesn't have height/weight directly, it has medical_data
        user_data = {
            "id": "test_user_123",
            "first_name": "Test",
            "last_name": "User",
            "email_address": "test@example.com",
            "password": "test_password123"
        }
        
        user = User(**user_data)
        
        assert user.id == user_data["id"]
        assert user.first_name == user_data["first_name"]
        assert user.email_address == user_data["email_address"]
        assert user.is_verified is False  # Default value
        assert user.is_active is True  # Default value
    
    def test_user_model_invalid_email(self, sample_user_data):
        """Test User model with invalid email."""
        src_models_user = pytest.importorskip("src.models.user")
        User = src_models_user.User
        
        sample_user_data["email_address"] = "invalid_email"
        
        with pytest.raises(ValidationError):
            User(**sample_user_data)
    
    def test_user_model_missing_required_fields(self):
        """Test User model with missing required fields."""
        src_models_user = pytest.importorskip("src.models.user")
        User = src_models_user.User
        
        incomplete_data = {
            "first_name": "Test"
            # Missing required fields
        }
        
        with pytest.raises(ValidationError):
            User(**incomplete_data)
    
    def test_partial_user_model(self):
        """Test PartialUser model for updates."""
        src_models_user = pytest.importorskip("src.models.user")
        PartialUser = src_models_user.PartialUser
        
        # PartialUser requires first_name and email_address as required fields
        partial_data = {
            "first_name": "Updated",
            "email_address": "updated@example.com"
        }
        
        partial_user = PartialUser(**partial_data)
        
        assert partial_user.first_name == "Updated"
        assert partial_user.email_address == "updated@example.com"
    
    def test_user_medical_model(self):
        """Test UserMedical model."""
        src_models_user = pytest.importorskip("src.models.user")
        UserMedical = src_models_user.UserMedical
        
        from datetime import datetime
        
        medical_data = {
            "date_of_birth": datetime(1990, 1, 1),
            "height": 165.0,
            "pre_pregnancy_weight": 60.0,
            "current_weight": 65.0,
            "pre_existing_conditions": ["diabetes", "hypertension"],
            "food_intolerances": ["nuts", "shellfish"],
            "dietary_preferences": ["vegetarian", "low-sodium"]
        }
        
        user_medical = UserMedical(**medical_data)
        
        assert user_medical.height == 165.0
        assert len(user_medical.pre_existing_conditions) == 2
        assert "diabetes" in user_medical.pre_existing_conditions
        assert user_medical.current_weight == 65.0