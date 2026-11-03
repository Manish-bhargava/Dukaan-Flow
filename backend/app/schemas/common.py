from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Standard success envelope (docs/API_DESIGN.MD)."""

    success: bool = True
    message: str
    data: T
