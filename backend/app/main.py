from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.v1.dev.fake_sms_routes import create_development_fake_sms_router
from app.api.v1.dev.fake_password_reset_routes import (
    create_development_fake_password_reset_router,
)
from app.core.config import (
    Settings,
    allowed_frontend_origins,
    settings,
    validate_runtime_security,
)
from app.integrations.development_fake_sms import (
    DevelopmentFakeSmsStore,
    development_fake_sms_store,
)
from app.integrations.password_reset_delivery import (
    DevelopmentFakePasswordResetStore,
    development_fake_password_reset_store,
)

STATUS = {"application": "UniShop China API", "status": "running", "version": "1.0.0"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


def create_app(
    config: Settings = settings,
    *,
    fake_sms_store: DevelopmentFakeSmsStore = development_fake_sms_store,
    fake_password_reset_store: DevelopmentFakePasswordResetStore = (
        development_fake_password_reset_store
    ),
) -> FastAPI:
    validate_runtime_security(config)
    environment = config.app_env.strip().lower()
    application = FastAPI(
        title=f"{config.app_name} API",
        version="1.0.0",
        debug=config.app_debug and environment == "development",
        lifespan=lifespan,
    )
    application.state.settings = config
    application.state.fake_password_reset_store = fake_password_reset_store
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_frontend_origins(config)),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )
    application.include_router(api_router, prefix=config.api_v1_prefix)
    if environment == "development" and config.enable_fake_sms_dev_inbox:
        application.include_router(
            create_development_fake_sms_router(fake_sms_store),
            prefix=f"{config.api_v1_prefix}/dev/fake-sms",
        )
    if (
        environment == "development"
        and config.password_reset_delivery_provider.strip().lower() == "fake"
        and config.enable_fake_password_reset_dev_inbox
    ):
        application.include_router(
            create_development_fake_password_reset_router(fake_password_reset_store),
            prefix=f"{config.api_v1_prefix}/dev/fake-password-reset",
        )

    no_store_paths = {
        f"{config.api_v1_prefix}/auth/login",
        f"{config.api_v1_prefix}/auth/refresh",
        f"{config.api_v1_prefix}/auth/password/forgot",
    }

    @application.middleware("http")
    async def protect_token_responses_from_caching(request: Request, call_next):
        response = await call_next(request)
        if request.method == "POST" and request.url.path in no_store_paths:
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

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
