"""Admin reports: one function per report returning (columns, rows), for JSON or CSV.

Sales are confirmed (APPROVED) orders by IST confirmation date, valued at their order totals
(line totals for product/category reports). A sale is credited to the salesman who placed the
order, else to the shop's assigned salesman.
"""

import csv
import io
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.constants import OrderStatus, UserRole
from app.core.permissions import ensure_role
from app.exceptions.base import AppException
from app.core.constants import ErrorCode
from app.models import Order, User
from app.modules.admin import repository
from app.modules.admin.monitoring import IST, ist_range
from app.modules.order_desk.service import salesman_of
from app.modules.settings.service import get_settings

Report = tuple[list[str], list[list]]
DEFAULT_DAYS = 30  # dated reports without dates: the last 30 days
MAX_DAYS = 366
ZERO = Decimal(0)
SOURCE_NAMES = {"MANUAL": "Retailer app", "SALESMAN": "Salesman app", "AI": "AI capture"}


def _money(v) -> str:
    return f"{Decimal(v):.2f}"


def _qty(v) -> str:
    return f"{Decimal(v).normalize():f}"


def _date(v: datetime | None) -> str:
    return v.astimezone(IST).strftime("%Y-%m-%d") if v else ""


def _sales(db, start, end) -> list[Order]:
    return repository.approved_orders_between(db, start, end)


def sales_by_date(db, start, end) -> Report:
    days: dict[str, list] = defaultdict(lambda: [0, ZERO])
    for o in _sales(db, start, end):
        d = days[_date(o.approved_at)]
        d[0] += 1
        d[1] += o.grand_total
    return ["Date", "Orders", "Sales"], [[k, v[0], _money(v[1])] for k, v in sorted(days.items())]


def _by_retailer(db, start, end) -> list[list]:
    rows: dict = {}
    for o in _sales(db, start, end):
        r = rows.setdefault(o.retailer_id, [o.retailer.shop_name, o.retailer.city, 0, ZERO])
        r[2] += 1
        r[3] += o.grand_total
    return sorted(rows.values(), key=lambda r: r[3], reverse=True)


def sales_by_retailer(db, start, end) -> Report:
    return ["Retailer", "City", "Orders", "Sales"], [[r[0], r[1], r[2], _money(r[3])] for r in _by_retailer(db, start, end)]


def top_retailers(db, start, end) -> Report:
    cols, rows = sales_by_retailer(db, start, end)
    return ["Rank", *cols], [[i + 1, *r] for i, r in enumerate(rows[:10])]


def sales_by_salesman(db, start, end) -> Report:
    rows: dict = {}
    for o in _sales(db, start, end):
        person = salesman_of(o)
        key = person.id if person else None
        r = rows.setdefault(key, [person.name if person else "No salesman", 0, ZERO, set()])
        r[1] += 1
        r[2] += o.grand_total
        r[3].add(o.retailer_id)
    data = sorted(rows.values(), key=lambda r: r[2], reverse=True)
    return ["Salesman", "Orders", "Sales", "Shops"], [[r[0], r[1], _money(r[2]), len(r[3])] for r in data]


def _by_product(db, start, end) -> list[list]:
    rows: dict = {}
    for o in _sales(db, start, end):
        for i in o.items:
            r = rows.setdefault(i.product_id, [i.sku, i.product_name, i.product.category.name, ZERO, ZERO, ZERO])
            r[3] += i.paid_quantity
            r[4] += i.free_quantity
            r[5] += i.line_total
    return sorted(rows.values(), key=lambda r: r[5], reverse=True)


def sales_by_product(db, start, end) -> Report:
    return (["SKU", "Product", "Category", "Cases sold", "Free cases", "Sales"],
            [[r[0], r[1], r[2], _qty(r[3]), _qty(r[4]), _money(r[5])] for r in _by_product(db, start, end)])


def top_products(db, start, end) -> Report:
    cols, rows = sales_by_product(db, start, end)
    return ["Rank", *cols], [[i + 1, *r] for i, r in enumerate(rows[:10])]


def sales_by_category(db, start, end) -> Report:
    rows: dict = {}
    for o in _sales(db, start, end):
        for i in o.items:
            r = rows.setdefault(i.product.category.name, [ZERO, ZERO, set()])
            r[0] += i.paid_quantity
            r[1] += i.line_total
            r[2].add(o.id)
    data = sorted(rows.items(), key=lambda kv: kv[1][1], reverse=True)
    return ["Category", "Cases sold", "Orders", "Sales"], [[k, _qty(v[0]), len(v[2]), _money(v[1])] for k, v in data]


def _statuses(orders: list[Order]) -> dict:
    out = defaultdict(lambda: [0, ZERO])
    for o in orders:
        out[o.status][0] += 1
        out[o.status][1] += o.grand_total
    return out


def source_breakdown(db, start, end) -> Report:
    by_source: dict = defaultdict(list)
    for o in repository.orders_created_between(db, start, end):
        by_source[o.source].append(o)
    rows = []
    for source, orders in sorted(by_source.items()):
        s = _statuses(orders)
        rows.append([SOURCE_NAMES.get(source, source), len(orders), s[OrderStatus.APPROVED][0], s[OrderStatus.REJECTED][0],
                     len(orders) - s[OrderStatus.APPROVED][0] - s[OrderStatus.REJECTED][0],
                     sum(1 for o in orders if o.created_offline), _money(s[OrderStatus.APPROVED][1])])
    return ["Source", "Orders", "Confirmed", "Rejected", "Open", "Created offline", "Confirmed value"], rows


def confirmed_vs_rejected(db, start, end) -> Report:
    orders = repository.orders_created_between(db, start, end)
    s = _statuses(orders)
    total = len(orders) or 1
    labels = {"APPROVED": "Confirmed", "REJECTED": "Rejected", "PENDING": "Under review", "CREDIT_HOLD": "Credit hold",
              "ON_HOLD": "On hold", "CLARIFICATION_REQUIRED": "Needs clarification"}
    return (["Status", "Orders", "Share %", "Value"],
            [[labels[k], v[0], f"{v[0] * 100 / total:.1f}", _money(v[1])] for k, v in
             sorted(s.items(), key=lambda kv: kv[1][0], reverse=True)])


def low_stock(db, start, end) -> Report:
    threshold = get_settings(db).low_stock_cases
    rows = repository.low_stock(db, threshold)
    return (["SKU", "Product", "Brand", "Stock (cases)", "Status"],
            [[p.sku, p.name, p.brand, _qty(s), "Out of stock" if s <= 0 else "Low"] for p, s in rows])


def credit_outstanding(db, start, end) -> Report:
    rows = []
    for r, account, last in repository.credit_report(db):
        rows.append([r.shop_name, r.assigned_salesman.name if r.assigned_salesman else "", _money(account.credit_limit),
                     _money(account.current_outstanding), _money(account.credit_limit - account.current_outstanding),
                     "Paused" if r.ordering_restricted_reason else ("Inactive" if not r.is_active else "Active"),
                     _date(last)])
    return ["Retailer", "Salesman", "Credit limit", "Outstanding", "Limit minus outstanding", "Ordering", "Last order"], rows


def inactive_retailers(db, start, end) -> Report:
    days = get_settings(db).inactive_retailer_days
    rows = repository.inactive_retailers(db, datetime.now(UTC) - timedelta(days=days))
    return (["Retailer", "Phone", "Salesman", "Last order", f"Days without order (>{days})"],
            [[r.shop_name, r.phone, r.assigned_salesman.name if r.assigned_salesman else "", _date(last) or "Never",
              (datetime.now(UTC) - last).days if last else ""] for r, last in rows])


def salesman_performance(db, start, end) -> Report:
    stats: dict = {u.id: [u.name, 0, 0, 0, 0, ZERO, 0] for u in repository.salesmen(db)}
    for v in repository.visits_between(db, start, end):
        if v.salesman_id in stats:
            stats[v.salesman_id][1] += 1
            stats[v.salesman_id][2] += 1 if v.order_id else 0
    for o in repository.orders_created_between(db, start, end):
        if o.created_by in stats:
            s = stats[o.created_by]
            s[3] += 1
            s[4] += 1 if o.status == OrderStatus.APPROVED else 0
            s[5] += o.grand_total if o.status == OrderStatus.APPROVED else ZERO
            s[6] += 1 if o.created_offline else 0
    rows = sorted(stats.values(), key=lambda s: s[5], reverse=True)
    return (["Salesman", "Visits", "Visits with order", "Conversion %", "Orders placed", "Confirmed", "Confirmed value",
             "Offline orders"],
            [[s[0], s[1], s[2], f"{(s[2] * 100 / s[1]) if s[1] else 0:.0f}", s[3], s[4], _money(s[5]), s[6]] for s in rows])


REPORTS: dict[str, tuple[str, Callable[..., Report], bool]] = {
    # name: (title, function, uses dates)
    "sales-by-date": ("Sales by date", sales_by_date, True),
    "sales-by-retailer": ("Sales by retailer", sales_by_retailer, True),
    "sales-by-salesman": ("Sales by salesman", sales_by_salesman, True),
    "sales-by-product": ("Sales by product", sales_by_product, True),
    "sales-by-category": ("Sales by category", sales_by_category, True),
    "source-breakdown": ("Order source breakdown", source_breakdown, True),
    "confirmed-vs-rejected": ("Confirmed vs rejected orders", confirmed_vs_rejected, True),
    "top-retailers": ("Top retailers", top_retailers, True),
    "top-products": ("Top products", top_products, True),
    "salesman-performance": ("Salesman performance", salesman_performance, True),
    "low-stock": ("Low-stock products", low_stock, False),
    "credit-outstanding": ("Credit / outstanding", credit_outstanding, False),
    "inactive-retailers": ("Retailers with no recent orders", inactive_retailers, False),
}


def run(db: Session, actor: User, name: str, from_date: date | None, to_date: date | None) -> dict:
    ensure_role(actor, UserRole.ADMIN)
    if name not in REPORTS:
        raise AppException(f"Unknown report '{name}'", ErrorCode.VALIDATION_ERROR, 422, {"reports": list(REPORTS)})
    title, fn, dated = REPORTS[name]
    if dated:
        # Reports read every order in the range: default to the last 30 days, at most a year.
        today = datetime.now(IST).date()
        to_date = to_date or today
        from_date = from_date or to_date - timedelta(days=DEFAULT_DAYS - 1)
        if (to_date - from_date).days >= MAX_DAYS:
            raise AppException(f"Choose at most {MAX_DAYS} days for a report", ErrorCode.VALIDATION_ERROR, 422,
                               {"max_days": MAX_DAYS})
    start, end = ist_range(from_date, to_date) if dated else (None, None)
    columns, rows = fn(db, start, end)
    return {"name": name, "title": title, "uses_dates": dated, "from_date": from_date if dated else None,
            "to_date": to_date if dated else None, "columns": columns, "rows": rows}


def _cell(value) -> str:
    text = str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t") and not _is_number(text) else text


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
        return True
    except Exception:
        return False


def to_csv(report: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(report["columns"])
    for row in report["rows"]:
        writer.writerow([_cell(v) for v in row])
    return buffer.getvalue()


def catalogue() -> list[dict]:
    return [{"name": k, "title": t, "uses_dates": d} for k, (t, _, d) in REPORTS.items()]
