"""Product images on Cloudinary: signed upload (httpx, no SDK) and optimized delivery URLs.

Only the backend talks to Cloudinary; the API secret never leaves the server. The database
keeps the original `secure_url` and `public_id`; the API returns delivery URLs with
`f_auto,q_auto` (best format/quality per browser) and `c_pad` (whole pack visible, padded
on white, never cropped). Non-Cloudinary URLs are returned unchanged, and products without
an image get null so the frontend shows its placeholder.
"""

import hashlib
import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.constants import ErrorCode
from app.exceptions.base import AppException

logger = logging.getLogger(__name__)

ALLOWED_TYPES = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "image/webp": b"RIFF"}
MAX_BYTES = 5 * 1024 * 1024
LARGE, THUMBNAIL = 800, 400  # square delivery sizes in px
_UPLOAD_MARKER = "/image/upload/"


@dataclass(frozen=True)
class StoredImage:
    secure_url: str
    public_id: str


def is_configured() -> bool:
    return bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=30)


def sign(params: dict[str, str], secret: str) -> str:
    """Cloudinary signature: SHA-1 of the sorted `key=value` pairs joined by `&`, plus the secret."""
    payload = "&".join(f"{key}={params[key]}" for key in sorted(params))
    return hashlib.sha1((payload + secret).encode()).hexdigest()


def validate(content: bytes, content_type: str | None) -> None:
    magic = ALLOWED_TYPES.get(content_type or "")
    if magic is None or not content.startswith(magic) or (content_type == "image/webp" and content[8:12] != b"WEBP"):
        raise AppException("Upload a JPEG, PNG or WebP image", ErrorCode.VALIDATION_ERROR, 422,
                           {"allowed": sorted(ALLOWED_TYPES)})
    if len(content) > MAX_BYTES:
        raise AppException("The image must be 5 MB or smaller", ErrorCode.VALIDATION_ERROR, 422,
                           {"max_bytes": MAX_BYTES})


def upload(content: bytes, content_type: str, public_id: str) -> StoredImage:
    """Upload (or replace) the image stored under `public_id`."""
    if not is_configured():
        raise AppException(
            "Image storage is not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and "
            "CLOUDINARY_API_SECRET in backend/.env and restart the server.",
            ErrorCode.IMAGE_STORAGE_NOT_CONFIGURED,
            503,
        )
    params = {"public_id": public_id, "overwrite": "true", "invalidate": "true", "timestamp": str(int(time.time()))}
    form = {**params, "api_key": settings.CLOUDINARY_API_KEY, "signature": sign(params, settings.CLOUDINARY_API_SECRET)}
    url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload"
    failed = AppException("The image could not be uploaded. Please try again.", ErrorCode.IMAGE_UPLOAD_FAILED, 502)
    try:
        with _http_client() as client:
            response = client.post(url, data=form, files={"file": ("image", content, content_type)})
    except httpx.HTTPError as exc:
        logger.warning("Cloudinary upload failed: %s", type(exc).__name__)
        raise failed from None
    if response.status_code != 200:
        message = ""
        if response.headers.get("content-type", "").startswith("application/json"):
            message = (response.json().get("error") or {}).get("message", "")
        logger.warning("Cloudinary upload rejected: HTTP %s %s", response.status_code, message)
        raise failed
    body = response.json()
    if not body.get("secure_url") or not body.get("public_id"):
        logger.warning("Cloudinary upload response missing secure_url/public_id")
        raise failed
    return StoredImage(secure_url=body["secure_url"], public_id=body["public_id"])


def delivery_url(url: str | None, size: int) -> str | None:
    """Optimized square delivery URL for a Cloudinary image; other URLs unchanged."""
    if not url or "res.cloudinary.com" not in url or _UPLOAD_MARKER not in url:
        return url
    head, tail = url.split(_UPLOAD_MARKER, 1)
    return f"{head}{_UPLOAD_MARKER}f_auto,q_auto,c_pad,b_white,w_{size},h_{size}/{tail}"
