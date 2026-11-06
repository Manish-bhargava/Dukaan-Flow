"""Audit log for master-data changes (retailers, products, prices, schemes, stock, credit,
users, assignments, settings) and failed salesman syncs. Order actions are recorded in
order_events by the orders service; the Admin audit view shows both."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _plain(value: Any) -> Any:
    """JSON-safe copy of a value (Decimal, UUID, datetime → str)."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def changes(before: dict, after: dict) -> dict:
    """Only the fields that changed: {"field": {"from": x, "to": y}}."""
    return {k: {"from": _plain(before.get(k)), "to": _plain(after.get(k))}
            for k in after if _plain(before.get(k)) != _plain(after.get(k))}


def record(db: Session, actor: User | None, action: str, entity_type: str, entity_id: Any = None,
           entity_label: str | None = None, details: dict | None = None) -> None:
    """Add an audit entry to the session (the caller's transaction commits it)."""
    db.add(AuditLog(
        actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        entity_label=(entity_label or "")[:200] or None, details=_plain(details) if details else None,
        created_at=datetime.now(UTC),
    ))
