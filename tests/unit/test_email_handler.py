"""
Unit tests for email handler utility.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import os

pytestmark = pytest.mark.unit


class TestEmailHandler:
    """Test cases for email handling functionality."""
    
    @pytest.mark.asyncio
    async def test_send_otp_mail_success(self, mock_email_handler):
        """Test successful OTP email sending."""
        # Mock the send function at module level
        with patch("src.utils.email_handler.send") as mock_send:
            mock_send.return_value = None  # aiosmtplib.send returns None on success
            
            from src.utils.email_handler import send_otp_mail
            
            email = "test@example.com"
            otp = "123456"
            
            # Should not raise any exception
            await send_otp_mail(email, otp)
            
            # Verify send was called
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_otp_mail_failure(self):
        """Test OTP email sending failure."""
        from src.utils.email_handler import send_otp_mail
        
        email = "test@example.com"
        otp = "123456"
        
        with patch("src.utils.email_handler.send") as mock_send:
            mock_send.side_effect = Exception("SMTP Error")
            
            # Should raise an exception
            with pytest.raises(Exception):
                await send_otp_mail(email, otp)
    
    def test_email_content_formatting(self):
        """Test that OTP content is properly formatted."""
        # This tests that the HTML template loading works
        from src.utils import email_handler
        
        # Check that OTP_CONTENT is loaded
        assert hasattr(email_handler, 'OTP_CONTENT')
        assert isinstance(email_handler.OTP_CONTENT, str)
        assert len(email_handler.OTP_CONTENT) > 0
    
    def test_email_constants(self):
        """Test email configuration constants."""
        from src.utils import email_handler
        
        assert email_handler.EMAIL_HOST == "smtp.gmail.com"
        assert email_handler.EMAIL_PORT == 587
        assert email_handler.EMAIL_FROM == "MomCare <no-reply@momcare.com>"
    
    @pytest.mark.asyncio 
    async def test_email_message_structure(self):
        """Test that email message is structured correctly."""
        from email.message import EmailMessage
        
        email = "test@example.com"
        otp = "123456"
        
        with patch("src.utils.email_handler.send") as mock_send:
            mock_send.return_value = None
            
            from src.utils.email_handler import send_otp_mail
            await send_otp_mail(email, otp)
            
            # Verify that send was called with an EmailMessage
            args, kwargs = mock_send.call_args
            message = args[0]
            
            assert isinstance(message, EmailMessage)
            assert message["To"] == email
            assert message["From"] == "MomCare <no-reply@momcare.com>"
            assert message["Subject"] == "Your MomCare OTP - Secure Access"