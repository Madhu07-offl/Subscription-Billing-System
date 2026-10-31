import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registers every model)
from app.config import get_settings
from app.core.errors import register_error_handlers
from app.routers import auth, health, subscriptions

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Brightloop Subscription Billing API",
        version="1.0.0",
        docs_url="/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(subscriptions.router)
    application.include_router(api)
    return application


app = create_app()
