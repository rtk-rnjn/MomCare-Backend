from __future__ import annotations

import os
from email.message import EmailMessage

from aiosmtplib import send

with open("static/otp-content.html", "r") as file:
    OTP_CONTENT = file.read()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", 587))
EMAIL_FROM = os.getenv("EMAIL_FROM", "MomCare <no-reply@momcare.com>")


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
