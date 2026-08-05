from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.v1.dev.fake_sms_routes import create_development_fake_sms_router
from app.core.config import Settings, settings, validate_runtime_security
from app.integrations.development_fake_sms import (
    DevelopmentFakeSmsStore,
    development_fake_sms_store,
)

STATUS = {"application": "UniShop China API", "status": "running", "version": "1.0.0"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


def create_app(
    config: Settings = settings,
    *,
    fake_sms_store: DevelopmentFakeSmsStore = development_fake_sms_store,
) -> FastAPI:
    validate_runtime_security(config)
    environment = config.app_env.strip().lower()
    application = FastAPI(
        title=f"{config.app_name} API",
        version="1.0.0",
        debug=config.app_debug and environment == "development",
        lifespan=lifespan,
    )
    allowed_origins = [config.frontend_url]
    if environment == "development":
        allowed_origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
    application.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(set(allowed_origins)),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=config.api_v1_prefix)
    if environment == "development" and config.enable_fake_sms_dev_inbox:
        application.include_router(
            create_development_fake_sms_router(fake_sms_store),
            prefix=f"{config.api_v1_prefix}/dev/fake-sms",
        )

    @application.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return STATUS

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return STATUS

    @application.exception_handler(Exception)
    async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return application


app = create_app()
