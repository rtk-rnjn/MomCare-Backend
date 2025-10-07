from __future__ import annotations

import os
from email.message import EmailMessage

from aiosmtplib import send


class EmailHandler:
    with open("src/static/otp-content.html", "r") as file:
        OTP_CONTENT = file.read()

    EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
    EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

    EMAIL_HOST = "smtp.gmail.com"
    EMAIL_PORT = 587
    EMAIL_FROM = "MomCare <no-reply@momcare.com>"

    async def send_otp_mail(self, email_address: str, otp: str) -> bool:
        message = EmailMessage()
        message["From"] = self.EMAIL_FROM
        message["To"] = email_address
        message["Subject"] = "Your MomCare OTP - Secure Access"

        message.set_content(self.OTP_CONTENT.format(otp=otp), subtype="html")

        try:
            await send(
                message,
                hostname=self.EMAIL_HOST,
                port=self.EMAIL_PORT,
                start_tls=True,
                username=self.EMAIL_ADDRESS,
                password=self.EMAIL_PASSWORD,
            )
        except Exception as e:
            return False

        return True
