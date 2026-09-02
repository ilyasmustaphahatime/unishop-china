from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.v1.dev.fake_sms_routes import create_development_fake_sms_router
from app.api.v1.dev.fake_password_reset_routes import (
    create_development_fake_password_reset_router,
)
from app.api.v1.dev.fake_email_routes import create_development_fake_email_router
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
from app.integrations.email_verification_delivery import (
    DevelopmentFakeEmailVerificationStore,
    development_fake_email_verification_store,
)

STATUS = {"application": "UniShop China API", "status": "running", "version": "1.0.0"}
SAFE_VALIDATION_MESSAGES = {
    "missing": "Field required.",
    "extra_forbidden": "Extra inputs are not permitted.",
    "json_invalid": "Invalid JSON.",
}


def _safe_validation_segment(value: object, *, fallback: str) -> str | int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if (
        isinstance(value, str)
        and 0 < len(value) <= 64
        and value.isascii()
        and all(character.isalnum() or character in {"_", "-"} for character in value)
    ):
        return value
    return fallback


def safe_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Return useful validation metadata without echoing request-controlled values."""
    safe_errors: list[dict[str, Any]] = []
    for error in exc.errors():
        error_type = _safe_validation_segment(
            error.get("type"),
            fallback="validation_error",
        )
        if not isinstance(error_type, str):
            error_type = "validation_error"
        raw_location = error.get("loc")
        location = (
            [
                _safe_validation_segment(segment, fallback="field")
                for segment in raw_location
            ]
            if isinstance(raw_location, (tuple, list))
            else ["field"]
        )
        safe_errors.append(
            {
                "type": error_type,
                "loc": location,
                "msg": SAFE_VALIDATION_MESSAGES.get(error_type, "Invalid value."),
            }
        )
    return safe_errors


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
    fake_email_verification_store: DevelopmentFakeEmailVerificationStore = (
        development_fake_email_verification_store
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
    application.state.fake_email_verification_store = fake_email_verification_store
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
    if (
        environment == "development"
        and config.email_verification_delivery_provider.strip().lower() == "fake"
        and config.enable_fake_email_verification_dev_inbox
    ):
        application.include_router(
            create_development_fake_email_router(fake_email_verification_store),
            prefix=f"{config.api_v1_prefix}/dev/fake-email",
        )

    no_store_paths = {
        f"{config.api_v1_prefix}/auth/login",
        f"{config.api_v1_prefix}/auth/refresh",
        f"{config.api_v1_prefix}/auth/password/forgot",
        f"{config.api_v1_prefix}/auth/password/reset",
        f"{config.api_v1_prefix}/auth/password/change",
        f"{config.api_v1_prefix}/auth/email/resend-code",
        f"{config.api_v1_prefix}/auth/email/verify",
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

    @application.exception_handler(RequestValidationError)
    async def request_validation_exception(
        _: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": safe_validation_errors(exc)},
        )

    return application


app = create_app()
