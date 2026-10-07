"""Shared HTTP identity budgets; domains keep their own limits and error contracts."""
from collections.abc import Callable
from typing import NoReturn

from fastapi import Request

from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_rate_limit_value


def enforce_authenticated_limit(
    request: Request,
    user_id: str,
    *,
    ip_limiter: InMemoryRateLimiter,
    user_limiter: InMemoryRateLimiter,
    namespace: str,
    on_rejected: Callable[[int | None], NoReturn],
) -> None:
    peer = request.client.host if request.client is not None else "unknown"
    decision = ip_limiter.consume(peer)
    if not decision.allowed:
        on_rejected(decision.retry_after_seconds)
    config = getattr(request.app.state, "settings", settings)
    if config.jwt_secret_key is None:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")
    key = hash_rate_limit_value(user_id, config.jwt_secret_key, namespace=namespace)
    decision = user_limiter.consume(key)
    if not decision.allowed:
        on_rejected(decision.retry_after_seconds)
