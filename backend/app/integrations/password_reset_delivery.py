from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Literal, Protocol

from pydantic import SecretStr

from app.common.datetime_utils import as_utc
from app.core.config import settings
from app.core.security import hash_rate_limit_value
from app.models.base import utc_now

PasswordResetDestinationKind = Literal["email", "phone"]


@dataclass(frozen=True, slots=True)
class PasswordResetDeliveryResult:
    delivered: bool
    provider: str
    request_id: str | None = None


class PasswordResetDeliveryProvider(Protocol):
    enabled: bool
    available: bool

    def deliver_reset_code(
        self,
        *,
        identifier: str,
        identifier_kind: PasswordResetDestinationKind,
        code: str,
        expires_at: datetime,
    ) -> PasswordResetDeliveryResult: ...


class DisabledPasswordResetDeliveryProvider:
    enabled = False
    available = False

    def deliver_reset_code(
        self,
        *,
        identifier: str,
        identifier_kind: PasswordResetDestinationKind,
        code: str,
        expires_at: datetime,
    ) -> PasswordResetDeliveryResult:
        return PasswordResetDeliveryResult(delivered=False, provider="disabled")


@dataclass(frozen=True, slots=True)
class DevelopmentFakePasswordResetMessage:
    message_id: str
    identifier_reference: str
    identifier_kind: PasswordResetDestinationKind
    code: str
    created_at: datetime
    available_at: datetime
    expires_at: datetime


class DevelopmentFakePasswordResetStore:
    """Bounded process-memory delivery store; it never retains a raw identifier."""

    def __init__(
        self,
        *,
        identifier_secret: SecretStr | str,
        delivery_delay_seconds: float,
        ttl_seconds: int,
        max_messages: int,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.identifier_secret = identifier_secret
        self.delivery_delay_seconds = delivery_delay_seconds
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages
        self.now_provider = now_provider
        self._messages: list[DevelopmentFakePasswordResetMessage] = []
        self._lock = RLock()

    def add(
        self,
        *,
        identifier: str,
        identifier_kind: PasswordResetDestinationKind,
        code: str,
        expires_at: datetime,
    ) -> DevelopmentFakePasswordResetMessage:
        now = as_utc(self.now_provider())
        reference = self._reference(identifier)
        effective_expiry = min(
            as_utc(expires_at),
            now + timedelta(seconds=self.ttl_seconds),
        )
        message = DevelopmentFakePasswordResetMessage(
            message_id=secrets.token_urlsafe(24),
            identifier_reference=reference,
            identifier_kind=identifier_kind,
            code=code,
            created_at=now,
            available_at=now + timedelta(seconds=self.delivery_delay_seconds),
            expires_at=effective_expiry,
        )
        with self._lock:
            self._cleanup_locked(now)
            self._messages = [
                existing
                for existing in self._messages
                if existing.identifier_reference != reference
            ]
            self._messages.append(message)
            if len(self._messages) > self.max_messages:
                self._messages = self._messages[-self.max_messages :]
        return message

    def latest_available(
        self,
        identifier: str,
    ) -> DevelopmentFakePasswordResetMessage | None:
        now = as_utc(self.now_provider())
        reference = self._reference(identifier)
        with self._lock:
            self._cleanup_locked(now)
            matches = [
                message
                for message in self._messages
                if message.identifier_reference == reference
                and message.available_at <= now
            ]
            return matches[-1] if matches else None

    def consume_message(self, message_id: str) -> bool:
        now = as_utc(self.now_provider())
        with self._lock:
            self._cleanup_locked(now)
            before = len(self._messages)
            self._messages = [
                message for message in self._messages if message.message_id != message_id
            ]
            return len(self._messages) != before

    def message_count(self) -> int:
        now = as_utc(self.now_provider())
        with self._lock:
            self._cleanup_locked(now)
            return len(self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()

    def _reference(self, identifier: str) -> str:
        return hash_rate_limit_value(
            identifier,
            self.identifier_secret,
            namespace="password-reset:fake-destination",
        )

    def _cleanup_locked(self, now: datetime) -> None:
        self._messages = [message for message in self._messages if message.expires_at > now]


class DevelopmentFakePasswordResetDeliveryProvider:
    enabled = True
    available = True

    def __init__(self, store: DevelopmentFakePasswordResetStore) -> None:
        self.store = store

    def deliver_reset_code(
        self,
        *,
        identifier: str,
        identifier_kind: PasswordResetDestinationKind,
        code: str,
        expires_at: datetime,
    ) -> PasswordResetDeliveryResult:
        message = self.store.add(
            identifier=identifier,
            identifier_kind=identifier_kind,
            code=code,
            expires_at=expires_at,
        )
        return PasswordResetDeliveryResult(
            delivered=True,
            provider="fake",
            request_id=message.message_id,
        )


development_fake_password_reset_store = DevelopmentFakePasswordResetStore(
    identifier_secret=settings.jwt_secret_key or "",
    delivery_delay_seconds=settings.fake_password_reset_delivery_delay_seconds,
    ttl_seconds=settings.fake_password_reset_inbox_ttl_seconds,
    max_messages=settings.fake_password_reset_inbox_max_messages,
)
