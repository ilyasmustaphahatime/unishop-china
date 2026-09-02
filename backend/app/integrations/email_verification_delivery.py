from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Protocol

from pydantic import SecretStr

from app.common.datetime_utils import as_utc
from app.core.config import settings
from app.core.security import hash_rate_limit_value
from app.models.base import utc_now


@dataclass(frozen=True, slots=True)
class EmailVerificationDeliveryResult:
    delivered: bool
    provider: str
    request_id: str | None = None


class EmailVerificationDeliveryProvider(Protocol):
    enabled: bool
    available: bool

    def deliver_verification_code(
        self,
        *,
        user_id: str,
        email: str,
        code: str,
        expires_at: datetime,
    ) -> EmailVerificationDeliveryResult: ...

    def consume_verification_code(self, *, user_id: str, code: str) -> None: ...


class DisabledEmailVerificationDeliveryProvider:
    enabled = False
    available = False

    def deliver_verification_code(
        self,
        *,
        user_id: str,
        email: str,
        code: str,
        expires_at: datetime,
    ) -> EmailVerificationDeliveryResult:
        return EmailVerificationDeliveryResult(delivered=False, provider="disabled")

    def consume_verification_code(self, *, user_id: str, code: str) -> None:
        return None


@dataclass(frozen=True, slots=True)
class DevelopmentFakeEmailVerificationMessage:
    message_id: str
    user_reference: str
    code: str
    created_at: datetime
    available_at: datetime
    expires_at: datetime


class DevelopmentFakeEmailVerificationStore:
    """Bounded, expiring, process-memory-only inbox scoped by authenticated user."""

    def __init__(
        self,
        *,
        user_reference_secret: SecretStr | str,
        delivery_delay_seconds: float,
        ttl_seconds: int,
        max_messages: int,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.user_reference_secret = user_reference_secret
        self.delivery_delay_seconds = delivery_delay_seconds
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages
        self.now_provider = now_provider
        self._messages: list[DevelopmentFakeEmailVerificationMessage] = []
        self._lock = RLock()

    def add(
        self,
        *,
        user_id: str,
        code: str,
        expires_at: datetime,
    ) -> DevelopmentFakeEmailVerificationMessage:
        now = as_utc(self.now_provider())
        reference = self._reference(user_id)
        message = DevelopmentFakeEmailVerificationMessage(
            message_id=secrets.token_urlsafe(24),
            user_reference=reference,
            code=code,
            created_at=now,
            available_at=now + timedelta(seconds=self.delivery_delay_seconds),
            expires_at=min(
                as_utc(expires_at),
                now + timedelta(seconds=self.ttl_seconds),
            ),
        )
        with self._lock:
            self._cleanup_locked(now)
            self._messages = [
                existing
                for existing in self._messages
                if existing.user_reference != reference
            ]
            self._messages.append(message)
            if len(self._messages) > self.max_messages:
                self._messages = self._messages[-self.max_messages :]
        return message

    def latest_available(
        self,
        user_id: str,
    ) -> DevelopmentFakeEmailVerificationMessage | None:
        now = as_utc(self.now_provider())
        reference = self._reference(user_id)
        with self._lock:
            self._cleanup_locked(now)
            matches = [
                message
                for message in self._messages
                if message.user_reference == reference and message.available_at <= now
            ]
            return matches[-1] if matches else None

    def consume_message(self, *, user_id: str, message_id: str) -> bool:
        now = as_utc(self.now_provider())
        reference = self._reference(user_id)
        with self._lock:
            self._cleanup_locked(now)
            before = len(self._messages)
            self._messages = [
                message
                for message in self._messages
                if not (
                    message.user_reference == reference
                    and message.message_id == message_id
                )
            ]
            return len(self._messages) != before

    def consume_code(self, *, user_id: str, code: str) -> bool:
        now = as_utc(self.now_provider())
        reference = self._reference(user_id)
        with self._lock:
            self._cleanup_locked(now)
            before = len(self._messages)
            self._messages = [
                message
                for message in self._messages
                if not (
                    message.user_reference == reference and message.code == code
                )
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

    def _reference(self, user_id: str) -> str:
        return hash_rate_limit_value(
            user_id,
            self.user_reference_secret,
            namespace="email-verification:fake-user",
        )

    def _cleanup_locked(self, now: datetime) -> None:
        self._messages = [message for message in self._messages if message.expires_at > now]


class DevelopmentFakeEmailVerificationProvider:
    enabled = True
    available = True

    def __init__(self, store: DevelopmentFakeEmailVerificationStore) -> None:
        self.store = store

    def deliver_verification_code(
        self,
        *,
        user_id: str,
        email: str,
        code: str,
        expires_at: datetime,
    ) -> EmailVerificationDeliveryResult:
        # The development store intentionally never retains the email address.
        message = self.store.add(
            user_id=user_id,
            code=code,
            expires_at=expires_at,
        )
        return EmailVerificationDeliveryResult(
            delivered=True,
            provider="fake",
            request_id=message.message_id,
        )

    def consume_verification_code(self, *, user_id: str, code: str) -> None:
        self.store.consume_code(user_id=user_id, code=code)


development_fake_email_verification_store = DevelopmentFakeEmailVerificationStore(
    user_reference_secret=settings.jwt_secret_key or "",
    delivery_delay_seconds=settings.fake_email_verification_delivery_delay_seconds,
    ttl_seconds=settings.fake_email_verification_inbox_ttl_seconds,
    max_messages=settings.fake_email_verification_inbox_max_messages,
)
