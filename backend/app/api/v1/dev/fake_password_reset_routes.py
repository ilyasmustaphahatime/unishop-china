import ipaddress
import math
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict

from app.integrations.password_reset_delivery import (
    DevelopmentFakePasswordResetStore,
    PasswordResetDestinationKind,
)
from app.models.base import utc_now
from app.schemas.auth import normalize_account_identifier

NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class DevelopmentFakePasswordResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    identifier_kind: PasswordResetDestinationKind
    code: str
    created_at: datetime
    expires_at: datetime
    expires_in_seconds: int


def _require_loopback(request: Request) -> None:
    host = request.client.host if request.client is not None else ""
    try:
        allowed = ipaddress.ip_address(host).is_loopback
    except ValueError:
        allowed = False
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "LOCALHOST_REQUIRED", "message": "This route is local-only."},
            headers=NO_STORE_HEADERS,
        )


def create_development_fake_password_reset_router(
    store: DevelopmentFakePasswordResetStore,
) -> APIRouter:
    router = APIRouter(tags=["development-fake-password-reset"])

    @router.get("/latest", response_model=DevelopmentFakePasswordResetResponse)
    def latest_fake_password_reset(
        request: Request,
        response: Response,
        identifier: str | None = None,
    ) -> DevelopmentFakePasswordResetResponse:
        _require_loopback(request)
        if set(request.query_params) - {"identifier"}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "INVALID_QUERY", "message": "Unknown query parameter."},
                headers=NO_STORE_HEADERS,
            )
        try:
            normalized = normalize_account_identifier(identifier)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "INVALID_IDENTIFIER",
                    "message": "Enter a valid email address or mainland Chinese phone number.",
                },
                headers=NO_STORE_HEADERS,
            ) from exc
        if not isinstance(normalized, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "INVALID_IDENTIFIER",
                    "message": "Enter a valid email address or mainland Chinese phone number.",
                },
                headers=NO_STORE_HEADERS,
            )

        message = store.latest_available(normalized)
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "MESSAGE_NOT_AVAILABLE", "message": "No message is available."},
                headers=NO_STORE_HEADERS,
            )
        response.headers.update(NO_STORE_HEADERS)
        return DevelopmentFakePasswordResetResponse(
            message_id=message.message_id,
            identifier_kind=message.identifier_kind,
            code=message.code,
            created_at=message.created_at,
            expires_at=message.expires_at,
            expires_in_seconds=max(
                0,
                math.ceil((message.expires_at - utc_now()).total_seconds()),
            ),
        )

    @router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
    def consume_fake_password_reset(
        message_id: str,
        request: Request,
        response: Response,
    ) -> None:
        _require_loopback(request)
        store.consume_message(message_id)
        response.headers.update(NO_STORE_HEADERS)

    return router
