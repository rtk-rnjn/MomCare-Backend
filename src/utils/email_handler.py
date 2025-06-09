from __future__ import annotations

import os
from email.message import EmailMessage

from aiosmtplib import send

with open("static/otp-content.html", "r") as file:
    OTP_CONTENT = file.read()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


async def send_otp_mail(email_address: str, otp: str) -> None:
    """
    Sends an OTP email to the user.

    Args:
        email_address (str): The email address of the user.
        otp (str): The OTP to be sent.

    Returns:
        None
    """
    message = EmailMessage()
    message["From"] = EMAIL_ADDRESS
    message["To"] = email_address
    message["Subject"] = "Your MomCare OTP - Secure Access"
    message.set_content(OTP_CONTENT.format(otp=otp), subtype="html")

    await send(message, hostname="smtp.gmail.com", port=587, start_tls=True, username=EMAIL_ADDRESS, password=EMAIL_PASSWORD)
