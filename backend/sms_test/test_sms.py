import asyncio
from sms_service import send_otp_sms


async def main():

    print("DUKAANFLOW SMS TEST")

    phone = input(
        "Enter your Indian mobile number: "
    ).strip()

    print("Received input:", repr(phone))

    try:
        result = await send_otp_sms(
            phone_number=phone,
            otp="123456"
        )

        print("\nSMS accepted by Brevo!")
        print("Message ID:", result.get("messageId"))

    except Exception as error:
        print("\nSMS sending failed!")
        print("Error:", repr(error))


if __name__ == "__main__":
    asyncio.run(main())
