from fastapi import Depends, HTTPException, Request, status

from app.api.v1.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_rate_limit_value
from app.services.auth_service import SafeAuthenticatedUser
from app.services.profile_service import ProfileService

profile_write_ip_limiter = InMemoryRateLimiter(
    max_requests=settings.profile_write_ip_rate_limit_requests,
    window_seconds=settings.profile_write_rate_limit_window_seconds,
    max_keys=settings.profile_rate_limit_max_keys,
)
profile_write_user_limiter = InMemoryRateLimiter(
    max_requests=settings.profile_write_user_rate_limit_requests,
    window_seconds=settings.profile_write_rate_limit_window_seconds,
    max_keys=settings.profile_rate_limit_max_keys,
)
onboarding_ip_limiter = InMemoryRateLimiter(
    max_requests=settings.onboarding_ip_rate_limit_requests,
    window_seconds=settings.onboarding_rate_limit_window_seconds,
    max_keys=settings.profile_rate_limit_max_keys,
)
onboarding_user_limiter = InMemoryRateLimiter(
    max_requests=settings.onboarding_user_rate_limit_requests,
    window_seconds=settings.onboarding_rate_limit_window_seconds,
    max_keys=settings.profile_rate_limit_max_keys,
)
public_profile_ip_limiter = InMemoryRateLimiter(
    max_requests=settings.public_profile_ip_rate_limit_requests,
    window_seconds=settings.public_profile_rate_limit_window_seconds,
    max_keys=settings.profile_rate_limit_max_keys,
)


def get_profile_service() -> ProfileService:
    return ProfileService()


def enforce_profile_write_rate_limit(
    request: Request,
    current_user: SafeAuthenticatedUser = Depends(get_current_user),
) -> SafeAuthenticatedUser:
    _enforce_authenticated_limit(
        request,
        current_user,
        ip_limiter=profile_write_ip_limiter,
        user_limiter=profile_write_user_limiter,
        namespace="profile-write:user",
    )
    return current_user


def enforce_onboarding_rate_limit(
    request: Request,
    current_user: SafeAuthenticatedUser = Depends(get_current_user),
) -> SafeAuthenticatedUser:
    _enforce_authenticated_limit(
        request,
        current_user,
        ip_limiter=onboarding_ip_limiter,
        user_limiter=onboarding_user_limiter,
        namespace="profile-onboarding:user",
    )
    return current_user


def enforce_public_profile_rate_limit(request: Request) -> None:
    host = request.client.host if request.client is not None else "unknown"
    decision = public_profile_ip_limiter.consume(host)
    if not decision.allowed:
        _raise_rate_limit(decision.retry_after_seconds)


def _enforce_authenticated_limit(
    request: Request,
    current_user: SafeAuthenticatedUser,
    *,
    ip_limiter: InMemoryRateLimiter,
    user_limiter: InMemoryRateLimiter,
    namespace: str,
) -> None:
    host = request.client.host if request.client is not None else "unknown"
    ip_decision = ip_limiter.consume(host)
    if not ip_decision.allowed:
        _raise_rate_limit(ip_decision.retry_after_seconds)
    if settings.jwt_secret_key is None:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")
    key = hash_rate_limit_value(
        current_user.id,
        settings.jwt_secret_key,
        namespace=namespace,
    )
    user_decision = user_limiter.consume(key)
    if not user_decision.allowed:
        _raise_rate_limit(user_decision.retry_after_seconds)


def _raise_rate_limit(retry_after_seconds: int | None) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many profile requests. Please try again later.",
        headers={"Retry-After": str(retry_after_seconds or 1)},
    )
