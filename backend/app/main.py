import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, settings
from app.exceptions.handlers import register_exception_handlers
from app.modules.auth.router import router as auth_router
from app.modules.products.router import router as products_router
from app.utils.responses import success_response


def health_check() -> dict:
    """Liveness check: confirms the API process is running. Does not check the database."""
    return success_response("DukaanFlow API is running", {"status": "healthy"})


def create_app(app_settings: Settings = settings) -> FastAPI:
    # App warnings/errors (e.g. the development mock OTP) go to the console with their level
    # and source. Root stays at WARNING so library request logs (httpx) are not printed.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)-8s %(name)s: %(message)s")
    # Our own INFO lines (e.g. "Brevo accepted email … messageId=…") are shown too.
    for name in ("dukaanflow", "app"):
        logging.getLogger(name).setLevel(logging.INFO)
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
    api_router.include_router(auth_router)
    api_router.include_router(products_router)

    if app_settings.is_development:
        from app.modules.dev.router import router as dev_router

        api_router.include_router(dev_router)

    app.include_router(api_router)
    return app


app = create_app()
