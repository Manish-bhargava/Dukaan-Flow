from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, settings
from app.exceptions.handlers import register_exception_handlers
from app.utils.responses import success_response


def health_check() -> dict:
    """Liveness check: confirms the API process is running. Does not check the database."""
    return success_response("DukaanFlow API is running", {"status": "healthy"})


def create_app(app_settings: Settings = settings) -> FastAPI:
    app = FastAPI(title=app_settings.APP_NAME, debug=app_settings.DEBUG)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # All versioned endpoints are mounted under /api/v1. Module routers are included here.
    api_router = APIRouter(prefix=app_settings.API_V1_PREFIX)
    api_router.add_api_route("/health", health_check, methods=["GET"], tags=["health"])

    if app_settings.is_development:
        from app.modules.dev.router import router as dev_router

        api_router.include_router(dev_router)

    app.include_router(api_router)
    return app


app = create_app()
