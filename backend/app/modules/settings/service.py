"""Business settings (Admin). Only settings the application actually uses:

- business_*: shown on printed loading lists and the admin dashboard;
- low_stock_cases: below this a product is "low stock" (admin dashboard, stock, reports);
- inactive_retailer_days: no order for this many days = "not ordered recently";
- duplicate_window_hours / ai_low_confidence_percent: Order Desk warnings.

Stored one row per key in app_settings; missing keys use the defaults below.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, User


class BusinessSettings(BaseModel):
    business_name: str = Field(default="DukaanFlow Distributors", min_length=1, max_length=150)
    business_address: str = Field(default="", max_length=300)
    business_phone: str = Field(default="", max_length=20)
    business_gstin: str = Field(default="", max_length=20)
    low_stock_cases: int = Field(default=10, ge=0, le=100000)
    inactive_retailer_days: int = Field(default=14, ge=1, le=365)
    duplicate_window_hours: int = Field(default=24, ge=1, le=168)
    ai_low_confidence_percent: int = Field(default=80, ge=1, le=100)


def get_settings(db: Session) -> BusinessSettings:
    stored = {s.key: s.value for s in db.scalars(select(AppSetting))}
    known = {k: v for k, v in stored.items() if k in BusinessSettings.model_fields}
    return BusinessSettings(**known)


def save_settings(db: Session, actor: User, new: BusinessSettings) -> tuple[BusinessSettings, dict]:
    """Store all values; returns (settings, changed fields). The caller commits."""
    from app.modules.audit.service import changes

    old = get_settings(db)
    diff = changes(old.model_dump(), new.model_dump())
    now = datetime.now(UTC)
    for key, value in new.model_dump().items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value, updated_by=actor.id, updated_at=now))
        elif row.value != value:
            row.value, row.updated_by, row.updated_at = value, actor.id, now
    return new, diff
