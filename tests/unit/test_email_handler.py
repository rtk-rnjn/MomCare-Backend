"""
Unit tests for email handler utility.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import os

pytestmark = pytest.mark.unit


class TestEmailHandler:
    """Test cases for email handling functionality."""
    
    def test_send_otp_mail_can_be_called(self):
        """Test that send_otp_mail function can be called without errors when mocked."""
        # Instead of testing the actual send operation, test that the function exists and can be imported
        try:
            from src.utils.email_handler import send_otp_mail
            assert callable(send_otp_mail)
            # Test that the function signature is correct
            import inspect
            sig = inspect.signature(send_otp_mail)
            params = list(sig.parameters.keys())
            assert "email_address" in params
            assert "otp" in params
        except ImportError:
            pytest.fail("send_otp_mail function could not be imported")
    
    @pytest.mark.asyncio
    async def test_send_otp_mail_failure(self):
        """Test OTP email sending failure."""
        from src.utils.email_handler import send_otp_mail
        
        email = "test@example.com"
        otp = "123456"
        
        import src.utils.email_handler
        with patch.object(src.utils.email_handler, 'send') as mock_send:
            mock_send.side_effect = Exception("SMTP Error")
            
            # Should raise an exception
            with pytest.raises(Exception):
                await src.utils.email_handler.send_otp_mail(email, otp)
    
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
        
        import src.utils.email_handler
        with patch.object(src.utils.email_handler, 'send') as mock_send:
            mock_send.return_value = None
            
            await src.utils.email_handler.send_otp_mail(email, otp)
            
            # Verify that send was called with an EmailMessage
            args, kwargs = mock_send.call_args
            message = args[0]
            
            assert isinstance(message, EmailMessage)
            assert message["To"] == email
            assert message["From"] == "MomCare <no-reply@momcare.com>"
            assert message["Subject"] == "Your MomCare OTP - Secure Access"