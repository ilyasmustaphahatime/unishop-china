from contextlib import contextmanager
from fastapi import Depends, HTTPException, Request
from app.api.rate_limits import enforce_authenticated_limit
from app.api.v1.auth.dependencies import get_current_user
from app.core.authorization import AuthorizationError
from app.core.rate_limit import InMemoryRateLimiter
from app.services.catalog_service import CatalogError
from app.services.product_service import ProductError

product_peer_limiter = InMemoryRateLimiter(max_requests=120, window_seconds=60, max_keys=10000)
product_read_limiter = InMemoryRateLimiter(max_requests=60, window_seconds=60, max_keys=10000)
product_write_limiter = InMemoryRateLimiter(max_requests=30, window_seconds=60, max_keys=10000)


def listing_user(request: Request, user=Depends(get_current_user)):
    write = request.method in {"POST", "PATCH", "DELETE"}
    enforce_authenticated_limit(request, user.id, ip_limiter=product_peer_limiter,
        user_limiter=product_write_limiter if write else product_read_limiter,
        namespace="product-write:user" if write else "product-read:user", on_rejected=_reject)
    return user


def _reject(retry_after):
    raise HTTPException(429, "Too many listing requests.", headers={"Retry-After": str(retry_after or 1)})


@contextmanager
def safe_product_operation():
    try:
        yield
    except (ProductError, CatalogError, AuthorizationError) as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        # Intentional outer HTTP boundary: no SQL, request values, or driver logs.
        raise HTTPException(503, "Listing operation unavailable.") from None
