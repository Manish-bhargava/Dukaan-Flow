from typing import Any


def success_response(message: str, data: Any = None) -> dict[str, Any]:
    """Build the standard success envelope: {success, message, data}."""
    return {"success": True, "message": message, "data": data if data is not None else {}}


def error_response(
    message: str, error_code: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the standard error envelope: {success, message, error_code, details}."""
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "details": details or {},
    }
