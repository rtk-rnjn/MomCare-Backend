from __future__ import annotations

import os
from email.message import EmailMessage
from string import Template

import aiosmtplib
from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_FROM = "MomCare <no-reply@momcare.com>"


class EmailHandler:
    otp_content_template: Template
    forget_password_content_template: Template

    def __init__(self):
        self.refresh_template()

    def refresh_template(self):
        self.otp_content_template = self._load_template("src/utils/otp_content.html")
        self.forget_password_content_template = self._load_template(
            "src/utils/forget_password_content.html"
        )

    def _load_template(self, path: str) -> Template:
        with open(path, "r") as file:
            return Template(file.read())

    async def _send_email(self, *, to: str, subject: str, template: Template, otp: str):
        message = EmailMessage()
        message["From"] = EMAIL_FROM
        message["To"] = to
        message["Subject"] = subject

        content = template.safe_substitute(otp_code=otp)
        message.set_content(content, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=EMAIL_HOST,
            port=EMAIL_PORT,
            username=EMAIL_ADDRESS,
            password=EMAIL_PASSWORD,
            start_tls=True,
        )

    async def send_verification_email(self, *, to: str, subject: str, otp: str):
        await self._send_email(
            to=to,
            subject=subject,
            template=self.otp_content_template,
            otp=otp,
        )

    async def send_forget_password_email(self, *, to: str, subject: str, otp: str):
        await self._send_email(
            to=to,
            subject=subject,
            template=self.forget_password_content_template,
            otp=otp,
        )