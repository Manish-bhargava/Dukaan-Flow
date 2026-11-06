from dataclasses import asdict

from sqlalchemy.orm import Session

from app.models import User
from app.modules.retailers import service
from app.modules.retailers.schemas import CreditOut, PurchaseSummaryOut, RetailerProfileOut, SalesmanOut
from app.utils.responses import success_response


def my_profile(db: Session, user: User) -> dict:
    profile = service.get_my_profile(db, user)
    r, credit = profile.retailer, profile.credit
    salesman = r.assigned_salesman if r.assigned_salesman and r.assigned_salesman.is_active else None
    return success_response("Profile fetched successfully", RetailerProfileOut(
        id=r.id, shop_name=r.shop_name, owner_name=r.owner_name, phone=r.phone, address=r.address,
        city=r.city, gstin=r.gstin,
        assigned_salesman=SalesmanOut(name=salesman.name, phone=salesman.phone) if salesman else None,
        credit=CreditOut(**asdict(credit)) if credit else None,
        can_place_orders=credit is not None and credit.available_credit > 0 and not r.ordering_restricted_reason,
        ordering_restricted_reason=r.ordering_restricted_reason,
        purchases=PurchaseSummaryOut(**asdict(profile.purchases)),
    ))
