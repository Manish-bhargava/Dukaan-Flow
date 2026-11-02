from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.exceptions.handlers import register_exception_handlers
from app.utils.responses import success_response

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# All versioned endpoints are mounted under /api/v1. Module routers are included here.
api_router = APIRouter(prefix=settings.API_V1_PREFIX)


@api_router.get("/health", tags=["health"])
def health_check() -> dict:
    """Liveness check: confirms the API process is running. Does not check the database."""
    return success_response("DukaanFlow API is running", {"status": "healthy"})


app.include_router(api_router)
