"""Admin: retailers, credit, salesmen, assignments and users.

Every function takes the acting user (ADMIN only), validates the business rules, records an
audit entry and commits; on any failure it rolls back.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import ErrorCode, OrderStatus, UserRole
from app.core.permissions import ensure_role
from app.core.security import hash_password
from app.exceptions.base import AppException
from app.models import CreditAccount, Retailer, User
from app.modules.admin import repository
from app.modules.admin.schemas import (
    AssignmentInput,
    CreditUpdate,
    PasswordReset,
    RetailerCreate,
    RetailerUpdate,
    UserCreate,
    UserUpdate,
)
from app.modules.audit.service import changes, record
from app.modules.retailers import repository as retailers_repository
from app.modules.retailers.service import credit_summary

STAFF_ROLES = (UserRole.SALESMAN, UserRole.ORDER_DESK, UserRole.ADMIN)


def _not_found(what: str, identifier) -> AppException:
    return AppException(f"{what} not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"id": str(identifier)})


def _conflict(message: str, **details) -> AppException:
    return AppException(message, ErrorCode.CONFLICT, 409, details)


def _committed(db: Session, work):
    """Run `work()`, commit, roll back on failure (unique violations become 409)."""
    try:
        result = work()
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise _conflict("That value is already used by another record", detail=str(exc.orig).split("\n")[0]) from None
    except Exception:
        db.rollback()
        raise


def _ensure_phone_free(db: Session, phone: str, user_id: uuid.UUID | None = None) -> None:
    other = repository.user_by_phone(db, phone)
    if other is not None and other.id != user_id:
        raise _conflict(f"Mobile {phone} is already used by another account", field="phone")


def _ensure_email_free(db: Session, email: str | None, user_id: uuid.UUID | None = None) -> None:
    if email:
        other = repository.user_by_email(db, email)
        if other is not None and other.id != user_id:
            raise _conflict(f"Email {email} is already used by another account", field="email")


def _salesman(db: Session, salesman_id: uuid.UUID) -> User:
    user = db.get(User, salesman_id)
    if user is None or user.role != UserRole.SALESMAN:
        raise AppException("Salesman not found", ErrorCode.RESOURCE_NOT_FOUND, 404, {"id": str(salesman_id)})
    if not user.is_active:
        raise _conflict(f"{user.name} is inactive; retailers can only be assigned to active salesmen")
    return user


def _retailer(db: Session, retailer_id: uuid.UUID) -> Retailer:
    retailer = db.get(Retailer, retailer_id)
    if retailer is None:
        raise _not_found("Retailer", retailer_id)
    return retailer


def _retailer_snapshot(r: Retailer) -> dict:
    return {"shop_name": r.shop_name, "owner_name": r.owner_name, "phone": r.phone, "address": r.address,
            "city": r.city, "gstin": r.gstin, "salesman_id": r.assigned_salesman_id, "is_active": r.is_active}


# ---------------------------------------------------------------- retailers


def list_retailers(db: Session, actor: User, *, search, status, salesman_id, sort, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    if sort not in ("name", "newest", "outstanding", "last_order", "purchased"):
        raise AppException("Unknown sort", ErrorCode.VALIDATION_ERROR, 422)
    return repository.search_retailers(db, search=(search or "").strip() or None, status=status,
                                       salesman_id=salesman_id, sort=sort, offset=(page - 1) * limit, limit=limit)


def create_retailer(db: Session, actor: User, data: RetailerCreate) -> Retailer:
    """Retailer + its credit account + its login account (OTP to `email`)."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        _ensure_phone_free(db, data.phone)
        _ensure_email_free(db, data.email)
        salesman = _salesman(db, data.salesman_id) if data.salesman_id else None
        retailer = Retailer(shop_name=data.shop_name.strip(), owner_name=data.owner_name.strip(), phone=data.phone,
                            address=data.address.strip(), city=data.city.strip(),
                            gstin=(data.gstin or "").strip().upper() or None,
                            assigned_salesman_id=salesman.id if salesman else None)
        db.add(retailer)
        db.flush()
        db.add(CreditAccount(retailer_id=retailer.id, credit_limit=data.credit_limit, current_outstanding=Decimal(0)))
        db.add(User(name=retailer.owner_name, phone=data.phone, email=data.email, role=UserRole.RETAILER,
                    retailer_id=retailer.id))
        record(db, actor, "RETAILER_CREATED", "retailer", retailer.id, retailer.shop_name,
               {"after": {**_retailer_snapshot(retailer), "credit_limit": data.credit_limit, "email": data.email}})
        return retailer

    return _committed(db, work)


def get_retailer(db: Session, actor: User, retailer_id: uuid.UUID) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    retailer = _retailer(db, retailer_id)
    account = retailers_repository.get_credit_account(db, retailer.id)
    stats = retailers_repository.order_stats(db, retailer.id)
    return {
        "retailer": retailer,
        "credit": credit_summary(db, account) if account else None,
        "stats": stats,
        "users": repository.retailer_users(db, retailer.id),
        "recent_orders": repository.recent_orders(db, retailer_id=retailer.id, limit=10),
    }


def update_retailer(db: Session, actor: User, retailer_id: uuid.UUID, data: RetailerUpdate) -> Retailer:
    """Edit details, (un)assign the salesman, activate/deactivate. Deactivating also blocks
    the retailer's login; the retailer's login mobile/email follow the shop's."""
    ensure_role(actor, UserRole.ADMIN)
    fields = data.model_fields_set

    def work():
        retailer = _retailer(db, retailer_id)
        before = _retailer_snapshot(retailer)
        logins = repository.retailer_users(db, retailer.id)
        for name in ("shop_name", "owner_name", "address", "city"):
            if name in fields and getattr(data, name) is not None:
                setattr(retailer, name, getattr(data, name).strip())
        if "gstin" in fields:
            retailer.gstin = (data.gstin or "").strip().upper() or None
        if "phone" in fields and data.phone and data.phone != retailer.phone:
            for user in logins:
                if user.phone == retailer.phone:
                    _ensure_phone_free(db, data.phone, user.id)
                    user.phone = data.phone
            retailer.phone = data.phone
        if "email" in fields and logins:
            _ensure_email_free(db, data.email, logins[0].id)
            logins[0].email = data.email
        if "salesman_id" in fields:
            retailer.assigned_salesman_id = _salesman(db, data.salesman_id).id if data.salesman_id else None
        if "is_active" in fields and data.is_active is not None:
            retailer.is_active = data.is_active
            for user in logins:
                user.is_active = data.is_active
        diff = changes(before, _retailer_snapshot(retailer))
        if "email" in fields:
            diff["email"] = {"to": data.email}
        if diff:
            action = ("RETAILER_DEACTIVATED" if diff.get("is_active", {}).get("to") is False
                      else "RETAILER_ACTIVATED" if diff.get("is_active", {}).get("to") is True
                      else "ASSIGNMENT_CHANGED" if set(diff) == {"salesman_id"} else "RETAILER_UPDATED")
            record(db, actor, action, "retailer", retailer.id, retailer.shop_name, {"changes": diff})
        return retailer

    return _committed(db, work)


def update_credit(db: Session, actor: User, retailer_id: uuid.UUID, data: CreditUpdate) -> Retailer:
    """Credit limit and the ordering pause. Credit is still enforced on every order."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        retailer = _retailer(db, retailer_id)
        if data.credit_limit is not None:
            account = retailers_repository.get_credit_account(db, retailer.id, lock=True)
            if account is None:
                account = CreditAccount(retailer_id=retailer.id, credit_limit=data.credit_limit, current_outstanding=0)
                db.add(account)
                old = None
            else:
                old = account.credit_limit
                account.credit_limit = data.credit_limit
            if old != data.credit_limit:
                record(db, actor, "CREDIT_LIMIT_CHANGED", "credit", retailer.id, retailer.shop_name,
                       {"changes": {"credit_limit": {"from": old, "to": data.credit_limit}}, "reason": data.reason})
        if data.ordering_restricted is True:
            retailer.ordering_restricted_reason = data.reason.strip()
            record(db, actor, "ORDERING_RESTRICTED", "credit", retailer.id, retailer.shop_name,
                   {"reason": retailer.ordering_restricted_reason})
        elif data.ordering_restricted is False and retailer.ordering_restricted_reason:
            record(db, actor, "ORDERING_RESTORED", "credit", retailer.id, retailer.shop_name,
                   {"previous_reason": retailer.ordering_restricted_reason, "reason": data.reason})
            retailer.ordering_restricted_reason = None
        return retailer

    return _committed(db, work)


def credit_history(db: Session, actor: User, retailer_id: uuid.UUID):
    ensure_role(actor, UserRole.ADMIN)
    retailer = _retailer(db, retailer_id)
    changes_log, _ = repository.audit_entries(db, source="master", entity_type="credit", action=None,
                                              entity_id=str(retailer.id), actor_id=None, search=None, start=None,
                                              end=None, offset=0, limit=100)
    return {"ledger": repository.ledger(db, retailer.id), "changes": changes_log}


# ---------------------------------------------------------------- salesmen and assignments


def list_salesmen(db: Session, actor: User) -> list[dict]:
    ensure_role(actor, UserRole.ADMIN)
    since = datetime.now(UTC) - timedelta(days=30)
    assigned = repository.assigned_counts(db)
    orders = repository.salesman_order_stats(db, since)
    visit_stats = repository.visit_stats(db, since)
    last_visit = repository.last_visits(db)
    sync = repository.sync_statuses(db)
    return [{
        "user": u, "assigned": assigned.get(u.id, 0), "orders_30d": orders.get(u.id, (0, 0, 0)),
        "visits_30d": visit_stats.get(u.id, (0, 0, None)), "last_visit_at": last_visit.get(u.id), "sync": sync.get(u.id),
    } for u in repository.salesmen(db)]


def get_salesman(db: Session, actor: User, salesman_id: uuid.UUID) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    user = db.get(User, salesman_id)
    if user is None or user.role != UserRole.SALESMAN:
        raise _not_found("Salesman", salesman_id)
    since = datetime.now(UTC) - timedelta(days=30)
    return {
        "user": user,
        "retailers": repository.assigned_retailers(db, user.id),
        "orders_30d": repository.salesman_order_stats(db, since).get(user.id, (0, 0, 0)),
        "visits_30d": repository.visit_stats(db, since).get(user.id, (0, 0, None)),
        "sync": repository.sync_statuses(db).get(user.id),
        "visits": repository.visits(db, user.id, 50),
        "failures": [f for f in repository.sync_failures(db, limit=200) if f.actor_id == user.id][:20],
        "activity": repository.user_activity_counts(db, user.id),
    }


def assign(db: Session, actor: User, data: AssignmentInput) -> list[Retailer]:
    """Assign retailers to one salesman (or unassign). A retailer has one salesman, so
    assigning moves it from its previous salesman; both sides are in the audit entry."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        salesman = _salesman(db, data.salesman_id) if data.salesman_id else None
        names = {u.id: u.name for u in repository.salesmen(db)}
        moved = []
        for retailer_id in dict.fromkeys(data.retailer_ids):
            retailer = _retailer(db, retailer_id)
            old = retailer.assigned_salesman_id
            new = salesman.id if salesman else None
            if old == new:
                continue
            retailer.assigned_salesman_id = new
            record(db, actor, "ASSIGNMENT_CHANGED", "retailer", retailer.id, retailer.shop_name, {"changes": {
                "salesman": {"from": names.get(old), "to": names.get(new)},
                "salesman_id": {"from": old, "to": new}}})
            moved.append(retailer)
        return moved

    return _committed(db, work)


# ---------------------------------------------------------------- users


def list_users(db: Session, actor: User, *, role, search, status, page, limit):
    ensure_role(actor, UserRole.ADMIN)
    return repository.search_users(db, role=role, search=(search or "").strip() or None, status=status,
                                   offset=(page - 1) * limit, limit=limit)


def get_user(db: Session, actor: User, user_id: uuid.UUID) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("User", user_id)
    recent, _ = repository.audit_entries(db, source="all", entity_type=None, action=None, actor_id=user.id,
                                         search=None, start=None, end=None, offset=0, limit=15)
    return {"user": user, "activity": repository.user_activity_counts(db, user.id), "recent": recent}


def create_user(db: Session, actor: User, data: UserCreate) -> User:
    """Staff accounts (salesman, order desk, admin) with a password. Retailer logins are
    created with their retailer."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        _ensure_phone_free(db, data.phone)
        _ensure_email_free(db, data.email)
        user = User(name=data.name.strip(), phone=data.phone, email=data.email, role=data.role,
                    password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
        record(db, actor, "USER_CREATED", "user", user.id, user.name,
               {"after": {"name": user.name, "phone": user.phone, "email": user.email, "role": user.role}})
        return user

    return _committed(db, work)


def update_user(db: Session, actor: User, user_id: uuid.UUID, data: UserUpdate) -> User:
    """Rules: admins cannot change their own role or deactivate themselves; the last active
    admin stays; roles change only between staff roles; a salesman with assigned retailers
    must hand them over before being deactivated or changing role. Role changes and
    deactivation end the user's sessions at once (tokens are checked against the database)."""
    ensure_role(actor, UserRole.ADMIN)
    fields = data.model_fields_set

    def work():
        user = db.get(User, user_id)
        if user is None:
            raise _not_found("User", user_id)
        before = {"name": user.name, "phone": user.phone, "email": user.email, "role": user.role, "is_active": user.is_active}
        role_change = "role" in fields and data.role is not None and data.role != user.role
        deactivate = "is_active" in fields and data.is_active is False and user.is_active
        if user.id == actor.id and (role_change or deactivate):
            raise _conflict("You cannot change your own role or deactivate your own account")
        if (role_change or deactivate) and user.role == UserRole.ADMIN and repository.count_active_admins(db) <= 1:
            raise _conflict("At least one active admin is required")
        if role_change and user.role == UserRole.RETAILER:
            raise _conflict("Retailer logins cannot be given a staff role; create a staff account instead")
        if (role_change or deactivate) and user.role == UserRole.SALESMAN:
            count = len(repository.assigned_retailers(db, user.id))
            if count:
                raise _conflict(f"{user.name} has {count} assigned retailers; reassign them first",
                                assigned_retailers=count)
        if user.role == UserRole.RETAILER and "is_active" in fields and data.is_active and user.retailer and not user.retailer.is_active:
            raise _conflict("Activate the retailer to allow its login")
        if "name" in fields and data.name:
            user.name = data.name.strip()
        if "phone" in fields and data.phone:
            _ensure_phone_free(db, data.phone, user.id)
            user.phone = data.phone
        if "email" in fields:
            _ensure_email_free(db, data.email, user.id)
            user.email = data.email
        if role_change:
            user.role = data.role
        if "is_active" in fields and data.is_active is not None:
            user.is_active = data.is_active
        diff = changes(before, {"name": user.name, "phone": user.phone, "email": user.email, "role": user.role,
                                "is_active": user.is_active})
        if diff:
            action = "USER_ROLE_CHANGED" if "role" in diff else (
                "USER_DEACTIVATED" if diff.get("is_active", {}).get("to") is False else
                "USER_ACTIVATED" if diff.get("is_active", {}).get("to") is True else "USER_UPDATED")
            record(db, actor, action, "user", user.id, user.name, {"changes": diff})
        return user

    return _committed(db, work)


def reset_password(db: Session, actor: User, user_id: uuid.UUID, data: PasswordReset) -> User:
    """Set a new password for a staff account (retailers sign in with OTP)."""
    ensure_role(actor, UserRole.ADMIN)

    def work():
        user = db.get(User, user_id)
        if user is None:
            raise _not_found("User", user_id)
        if user.role not in STAFF_ROLES:
            raise _conflict("Retailers sign in with a one-time code; they have no password")
        user.password_hash = hash_password(data.new_password)
        record(db, actor, "PASSWORD_RESET", "user", user.id, user.name, None)  # never the password
        return user

    return _committed(db, work)


def open_statuses() -> tuple[str, ...]:
    return (OrderStatus.PENDING, OrderStatus.CREDIT_HOLD, OrderStatus.ON_HOLD, OrderStatus.CLARIFICATION_REQUIRED)
