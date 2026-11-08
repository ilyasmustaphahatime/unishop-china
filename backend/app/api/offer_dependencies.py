"""Existing JWT validation, strict query contracts and safe offer error boundary."""
from contextlib import contextmanager
import re
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from app.common.offers import OfferError
from app.core.authorization import AuthorizationError
from app.core.exceptions import RequestVerificationError, TokenValidationError
from app.core.session_security import validate_request_origin
from app.schemas.offer import DealListQuery, OfferListQuery, OfferStatus, Role
from app.schemas.conversation import ConversationRef
from app.services.token_service import AccessTokenService

bearer = HTTPBearer(auto_error=False)


@contextmanager
def safe_offer_operation():
    try:
        yield
    except OfferError as error:
        raise HTTPException(error.status, str(error), headers={"Retry-After": "60"} if error.status == 429 else None) from None
    except AuthorizationError as error:
        raise HTTPException(error.status, str(error)) from None
    except HTTPException:
        raise
    except Exception:
        # Deliberately no raw SQL, tokens, input values or private negotiation data.
        raise HTTPException(503, "Offer operation unavailable.") from None


def offer_actor(request: Request, credentials: HTTPAuthorizationCredentials | None = Security(bearer)):
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
        raise HTTPException(503, "Authentication unavailable.") from None
    try:
        origins = request.headers.getlist("origin")
        if len(origins) > 1:
            raise RequestVerificationError
        validate_request_origin(origins[0] if origins else None, config)
    except RequestVerificationError:
        raise HTTPException(403, "Request origin not allowed.") from None
    roots = (config.api_v1_prefix + "/offers", config.api_v1_prefix + "/deals")
    if request.query_params and not (request.method == "GET" and request.url.path in roots):
        raise HTTPException(422, "Unexpected query parameters.")
    return claims.subject


def query_model(request, model, **values):
    names = [name for name, _ in request.query_params.multi_items()]
    if (len(names) != len(set(names)) or any(n not in model.model_fields for n in names)
            or ("limit" in names and not re.fullmatch(r"[1-9][0-9]?", request.query_params["limit"]))):
        raise HTTPException(422, "Invalid pagination parameters.")
    try:
        return model(**values)
    except ValidationError:
        raise HTTPException(422, "Invalid pagination parameters.") from None


def offer_query(request: Request, limit: Annotated[int, Query(ge=1, le=50)] = 20,
                cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
                conversation_ref: Annotated[ConversationRef | None, Query()] = None,
                role: Annotated[Role | None, Query()] = None,
                status: Annotated[OfferStatus | None, Query()] = None):
    return query_model(request, OfferListQuery, limit=limit, cursor=cursor,
                       conversation_ref=conversation_ref, role=role, status=status)


def deal_query(request: Request, limit: Annotated[int, Query(ge=1, le=50)] = 20,
               cursor: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
               conversation_ref: Annotated[ConversationRef | None, Query()] = None,
               role: Annotated[Role | None, Query()] = None):
    return query_model(request, DealListQuery, limit=limit, cursor=cursor,
                       conversation_ref=conversation_ref, role=role)


Actor = Annotated[str, Depends(offer_actor)]
