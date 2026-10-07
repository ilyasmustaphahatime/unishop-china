from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from app.api.v1.auth.dependencies import get_current_user
from app.api.rate_limits import enforce_authenticated_limit
from app.core.authorization import AuthorizationError
from app.core.rate_limit import InMemoryRateLimiter
from app.services.catalog_service import CatalogError

admin_peer_limiter = InMemoryRateLimiter(max_requests=90, window_seconds=60, max_keys=10000)
admin_user_limiter = InMemoryRateLimiter(max_requests=30, window_seconds=60, max_keys=10000)


def catalog_admin(request: Request, user=Depends(get_current_user)):
    enforce_authenticated_limit(request, user.id, ip_limiter=admin_peer_limiter,
                                user_limiter=admin_user_limiter, namespace="catalog-admin:user",
                                on_rejected=_raise_rate_limit)
    # The service rechecks ACTIVE + DB role while holding locks until commit.
    return user


def _raise_rate_limit(retry_after: int | None):
    raise HTTPException(429, "Too many catalog requests. Please try again later.",
                        headers={"Retry-After": str(retry_after or 1)})


@contextmanager
def safe_catalog_operation():
    try:
        yield
    except (CatalogError, AuthorizationError) as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except IntegrityError as exc:
        if getattr(exc.orig, "args", (None,))[0] == 1062:
            raise HTTPException(409, "Catalog resource already exists.") from None
        raise HTTPException(503, "Catalog operation unavailable.") from None
    except HTTPException:
        raise
    except Exception:
        # Deliberate API boundary: DB/audit failures must not expose SQL, payloads
        # or driver details in responses or uncaught-exception logs.
        raise HTTPException(503, "Catalog operation unavailable.") from None
