"""Shared chat transport dependencies, not a dependency on another route module."""
from contextlib import contextmanager
import re
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.common.chat import ChatError
from app.core.authorization import AuthorizationError
from app.core.database import get_db
from app.core.exceptions import RequestVerificationError, TokenValidationError
from app.core.session_security import validate_request_origin
from app.schemas.conversation import ChatListQuery
from app.services.chat_service import ConversationService
from app.services.token_service import AccessTokenService

bearer_scheme = HTTPBearer(auto_error=False)


@contextmanager
def safe_chat_operation():
    try:
        yield
    except ChatError as exc:
        headers = {"Retry-After": "60"} if exc.status_code == 429 else None
        raise HTTPException(exc.status_code, exc.message, headers=headers) from None
    except AuthorizationError as exc:
        raise HTTPException(exc.status, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        # Do not log exceptions which may contain SQL parameters or private message/contact text.
        raise HTTPException(503, "Chat operation unavailable.") from None


def chat_actor(request: Request,
               credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
               db: Session = Depends(get_db)) -> str:
    if (credentials is None or credentials.scheme.lower() != "bearer"
            or not 1 <= len(credentials.credentials) <= 4096
            or len(request.headers.getlist("authorization")) != 1):
        raise HTTPException(401, "Invalid credentials.", headers={"WWW-Authenticate": "Bearer"})
    config = request.app.state.settings
    try:
        claims = AccessTokenService(config=config).decode_access_token(credentials.credentials)
    except TokenValidationError:
        raise HTTPException(401, "Invalid credentials.", headers={"WWW-Authenticate": "Bearer"}) from None
    except Exception:
        raise HTTPException(503, "Chat authentication unavailable.") from None
    origins = request.headers.getlist("origin")
    try:
        if len(origins) > 1:
            raise RequestVerificationError
        validate_request_origin(origins[0] if origins else None, config)
    except RequestVerificationError:
        raise HTTPException(403, "Request origin not allowed.") from None
    with safe_chat_operation():
        ConversationService(db, config=config).authenticate(claims.subject)
    path = request.url.path
    is_list = request.method == "GET" and (
        path == config.api_v1_prefix + "/chat/conversations" or path.endswith("/messages")
    )
    if request.query_params and not is_list:
        raise HTTPException(422, "Unexpected chat query parameters.")
    return claims.subject


def chat_query(request: Request,
               limit: Annotated[int, Query(ge=1, le=50)] = 20,
               cursor: Annotated[str | None, Query(max_length=512)] = None) -> ChatListQuery:
    names = [name for name, _ in request.query_params.multi_items()]
    if (len(names) != len(set(names)) or any(name not in {"limit", "cursor"} for name in names)
            or ("limit" in names and not re.fullmatch(r"[1-9][0-9]?", request.query_params["limit"]))):
        raise HTTPException(422, "Invalid chat pagination parameters.")
    return ChatListQuery(limit=limit, cursor=cursor)
