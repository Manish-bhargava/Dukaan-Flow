
import os
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

BREVO_API_URL = "https://api.brevo.com/v3/transactionalSMS/send"

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
SMS_SENDER = os.getenv("BREVO_SMS_SENDER", "DUKAANFLOW")


async def send_sms(phone_number: str, message: str):

    # Remove accidental spaces
    phone_number = phone_number.strip()

    # Validate Indian phone number
    if not re.fullmatch(r"\+91[6-9]\d{9}", phone_number):
        raise ValueError(
            "Invalid Indian phone number. "
            "Expected format: +919876543210"
        )

    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY missing in .env")

    payload = {
        "sender": SMS_SENDER,
        "recipient": phone_number,
        "content": message,
        "type": "transactional"
    }

    headers = {
        "api-key": BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json"
    }

    print("Sending SMS to:", phone_number)

    async with httpx.AsyncClient(timeout=20) as client:

        response = await client.post(
            BREVO_API_URL,
            headers=headers,
            json=payload
        )

        print("HTTP Status:", response.status_code)
        print("Brevo Response:", response.text)

        response.raise_for_status()

        return response.json()


async def send_otp_sms(phone_number: str, otp: str):

    return await send_sms(
        phone_number,
        f"Your DukaanFlow OTP is {otp}. "
        "Valid for 2 minutes. Do not share it."
    )
