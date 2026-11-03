from typing import Any

from app.core.constants import ErrorCode


class AppException(Exception):
    """Base class for expected application errors, rendered as the standard error response."""

    def __init__(
        self,
        message: str,
        error_code: str = ErrorCode.INTERNAL_SERVER_ERROR,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers
