from __future__ import annotations

import logging
import os
from email.message import EmailMessage

from aiosmtplib import send

with open("static/otp-content.html", "r") as file:
    OTP_CONTENT = file.read()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_FROM = "MomCare <no-reply@momcare.com>"

if EMAIL_ADDRESS is None or EMAIL_PASSWORD is None:
    logging.critical("Email credentials are not set in environment variables.")


async def send_otp_mail(email_address: str, otp: str) -> None:
    message = EmailMessage()
    message["From"] = EMAIL_FROM
    message["To"] = email_address
    message["Subject"] = "Your MomCare OTP - Secure Access"

    message.set_content(OTP_CONTENT.format(otp=otp), subtype="html")

    await send(
        message,
        hostname=EMAIL_HOST,
        port=EMAIL_PORT,
        start_tls=True,
        username=EMAIL_ADDRESS,
        password=EMAIL_PASSWORD,
    )
