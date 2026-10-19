"""Authentication, private budgets, bounded queries and safe HTTP errors."""
from contextlib import contextmanager
import re
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request

from app.api.rate_limits import enforce_authenticated_limit
from app.api.v1.auth.dependencies import get_current_user
from app.core.authorization import AuthorizationError
from app.core.rate_limit import InMemoryRateLimiter
from app.schemas.product_personalization import PersonalListQuery
from app.services.personalization_cursor import InvalidPersonalizationCursor
from app.services.personalization_errors import PersonalizationError

personal_peer_limiter = InMemoryRateLimiter(max_requests=180, window_seconds=60, max_keys=10000)
personal_read_limiter = InMemoryRateLimiter(max_requests=120, window_seconds=60, max_keys=10000)
personal_write_limiter = InMemoryRateLimiter(max_requests=60, window_seconds=60, max_keys=10000)


def _reject(retry_after):
    raise HTTPException(429, "Too many personal listing requests.",
                        headers={"Retry-After": str(retry_after or 1)})


def personal_user(request: Request, user=Depends(get_current_user)):
    write = request.method != "GET"
    enforce_authenticated_limit(request, user.id, ip_limiter=personal_peer_limiter,
        user_limiter=personal_write_limiter if write else personal_read_limiter,
        namespace="personal-write:user" if write else "personal-read:user", on_rejected=_reject)
    path = request.url.path
    lists = tuple(f"{request.app.state.settings.api_v1_prefix}/me/{name}"
                  for name in ("favorites", "recently-viewed"))
    if request.query_params and not (request.method == "GET" and path in lists):
        raise HTTPException(422, "Invalid personal listing parameters.")
    return user


def personal_query(request: Request,
                   limit: Annotated[int, Query(ge=1, le=50)] = 24,
                   cursor: Annotated[str | None, Query(max_length=512)] = None):
    names = [key for key, _ in request.query_params.multi_items()]
    if (len(names) != len(set(names)) or any(key not in {"limit", "cursor"} for key in names)
            or ("limit" in names and not re.fullmatch(r"[1-9][0-9]?", request.query_params["limit"]))):
        raise HTTPException(422, "Invalid personal listing parameters.")
    return PersonalListQuery(limit=limit, cursor=cursor)


@contextmanager
def safe_personal_operation():
    try:
        yield
    except InvalidPersonalizationCursor:
        raise HTTPException(400, "Invalid cursor.") from None
    except (PersonalizationError, AuthorizationError) as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        # HTTP boundary only: never echo or log driver, token or private-list data.
        raise HTTPException(503, "Personal listing operation unavailable.") from None
