from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.database import get_db
from app.core.exceptions import TokenValidationError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_rate_limit_identifier
from app.integrations.sms_client import (
    DisabledSmsSender,
    SmsConfigurationError,
    SmsSender,
    TencentSmsConfig,
    TencentSmsSender,
    UnavailableSmsSender,
)
from app.integrations.development_fake_sms import (
    DevelopmentFakeSmsSender,
    DevelopmentFakeSmsStore,
    development_fake_sms_store,
)
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthenticationService, RegistrationService, SafeAuthenticatedUser
from app.services.phone_verification_service import PhoneVerificationService
from app.services.token_service import AccessTokenService

registration_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.registration_rate_limit_requests,
    window_seconds=settings.registration_rate_limit_window_seconds,
    max_keys=settings.registration_rate_limit_max_clients,
)
login_ip_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.login_ip_rate_limit_requests,
    window_seconds=settings.login_ip_rate_limit_window_seconds,
    max_keys=settings.login_rate_limit_max_keys,
)
login_identifier_rate_limiter = InMemoryRateLimiter(
    max_requests=settings.login_identifier_rate_limit_requests,
    window_seconds=settings.login_identifier_rate_limit_window_seconds,
    max_keys=settings.login_rate_limit_max_keys,
)
bearer_scheme = HTTPBearer(auto_error=False)


def _secret_present(value: object) -> bool:
    return value is not None and bool(value.get_secret_value().strip())


def build_sms_sender(
    config: Settings,
    *,
    fake_store: DevelopmentFakeSmsStore | None = None,
) -> SmsSender:
    if not config.sms_enabled:
        return DisabledSmsSender()
    provider = config.sms_provider.strip().lower()
    if provider == "fake":
        if config.app_env.strip().lower() != "development":
            return UnavailableSmsSender()
        return DevelopmentFakeSmsSender(fake_store or development_fake_sms_store)
    if provider != "tencent":
        return UnavailableSmsSender()

    try:
        tencent_config = build_tencent_sms_config(config)
    except SmsConfigurationError:
        return UnavailableSmsSender()
    return TencentSmsSender(tencent_config)


def build_tencent_sms_config(config: Settings) -> TencentSmsConfig:
    checks = {
        "TENCENT_SECRET_ID": _secret_present(config.tencent_secret_id),
        "TENCENT_SECRET_KEY": _secret_present(config.tencent_secret_key),
        "TENCENT_SMS_SDK_APP_ID": bool((config.tencent_sms_sdk_app_id or "").strip()),
        "TENCENT_SMS_SIGNATURE": bool((config.tencent_sms_signature or "").strip()),
        "TENCENT_SMS_TEMPLATE_ID": bool((config.tencent_sms_template_id or "").strip()),
    }
    missing = [name for name, present in checks.items() if not present]
    if missing:
        raise SmsConfigurationError(missing)
    return TencentSmsConfig(
        secret_id=config.tencent_secret_id,
        secret_key=config.tencent_secret_key,
        sdk_app_id=config.tencent_sms_sdk_app_id.strip(),
        signature=config.tencent_sms_signature.strip(),
        template_id=config.tencent_sms_template_id.strip(),
        region=config.tencent_sms_region,
        endpoint=config.tencent_sms_endpoint,
        timeout_seconds=config.sms_request_timeout_seconds,
    )


def get_sms_sender() -> SmsSender:
    return build_sms_sender(settings)


def get_registration_rate_limiter() -> InMemoryRateLimiter:
    return registration_rate_limiter


def get_login_ip_rate_limiter() -> InMemoryRateLimiter:
    return login_ip_rate_limiter


def get_login_identifier_rate_limiter() -> InMemoryRateLimiter:
    return login_identifier_rate_limiter


def enforce_registration_rate_limit(
    request: Request,
    limiter: InMemoryRateLimiter = Depends(get_registration_rate_limiter),
) -> None:
    client_host = request.client.host if request.client is not None else "unknown"
    decision = limiter.consume(client_host)
    if not decision.allowed:
        retry_after = str(decision.retry_after_seconds or 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "REGISTRATION_RATE_LIMITED",
                "message": "Too many registration attempts. Please try again later.",
            },
            headers={"Retry-After": retry_after},
        )


def enforce_login_rate_limit(
    login_request: LoginRequest,
    request: Request,
    ip_limiter: InMemoryRateLimiter = Depends(get_login_ip_rate_limiter),
    identifier_limiter: InMemoryRateLimiter = Depends(get_login_identifier_rate_limiter),
) -> LoginRequest:
    client_host = request.client.host if request.client is not None else "unknown"
    ip_decision = ip_limiter.consume(client_host)
    if not ip_decision.allowed:
        _raise_login_rate_limit(ip_decision.retry_after_seconds)

    if settings.jwt_secret_key is None:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")
    identifier_key = hash_rate_limit_identifier(
        login_request.identifier,
        settings.jwt_secret_key,
    )
    identifier_decision = identifier_limiter.consume(identifier_key)
    if not identifier_decision.allowed:
        _raise_login_rate_limit(identifier_decision.retry_after_seconds)
    return login_request


def _raise_login_rate_limit(retry_after_seconds: int | None) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts. Please try again later.",
        headers={"Retry-After": str(retry_after_seconds or 1)},
    )


def get_registration_service(
    sms_sender: SmsSender = Depends(get_sms_sender),
) -> RegistrationService:
    return RegistrationService(
        verification_code_hash_secret=settings.verification_code_hash_secret,
        sms_sender=sms_sender,
    )


def get_access_token_service() -> AccessTokenService:
    return AccessTokenService(settings)


def get_authentication_service(
    token_service: AccessTokenService = Depends(get_access_token_service),
) -> AuthenticationService:
    return AuthenticationService(token_service=token_service)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: Session = Depends(get_db),
    token_service: AccessTokenService = Depends(get_access_token_service),
    service: AuthenticationService = Depends(get_authentication_service),
) -> SafeAuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _credentials_exception()
    try:
        claims = token_service.decode_access_token(credentials.credentials)
        current_user = service.load_current_user(session, claims.subject)
    except TokenValidationError as exc:
        raise _credentials_exception() from exc
    except Exception as exc:
        raise _credentials_exception() from exc
    if current_user is None:
        raise _credentials_exception()
    return current_user


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_phone_verification_service(
    sms_sender: SmsSender = Depends(get_sms_sender),
) -> PhoneVerificationService:
    return PhoneVerificationService(
        sms_sender=sms_sender,
        verification_code_hash_secret=settings.verification_code_hash_secret,
    )
