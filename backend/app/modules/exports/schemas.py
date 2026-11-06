import uuid
from datetime import date

from pydantic import BaseModel, Field


class TallyExportInput(BaseModel):
    from_date: date | None = None  # IST confirmation dates, inclusive
    to_date: date | None = None
    order_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    include_exported: bool = False  # True: export again orders already exported
