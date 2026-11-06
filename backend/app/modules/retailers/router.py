from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.modules.retailers import controller
from app.modules.retailers.schemas import RetailerProfileOut
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/retailers", tags=["retailers"])


@router.get("/me", response_model=ApiResponse[RetailerProfileOut])
def my_profile(db: DbSession, user: CurrentUser):
    """The signed-in retailer's details, credit position and purchase summary (RETAILER only)."""
    return controller.my_profile(db, user)
