from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Literal

from app.common.datetime_utils import as_utc
from app.core.config import settings
from app.integrations.sms_client import SmsDeliveryResult
from app.models.base import utc_now

DeliveryType = Literal["registration", "resend"]


@dataclass(frozen=True, slots=True)
class DevelopmentFakeSmsMessage:
    message_id: str
    phone_number: str
    code: str
    delivery_type: DeliveryType
    created_at: datetime
    available_at: datetime
    expires_at: datetime


class DevelopmentFakeSmsStore:
    """Thread-safe, process-memory-only OTP inbox for local development."""

    def __init__(
        self,
        *,
        delivery_delay_seconds: float,
        ttl_seconds: int,
        max_messages: int,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.delivery_delay_seconds = delivery_delay_seconds
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages
        self.now_provider = now_provider
        self._messages: list[DevelopmentFakeSmsMessage] = []
        self._lock = RLock()

    def add(
        self,
        phone_number: str,
        code: str,
        delivery_type: DeliveryType,
    ) -> DevelopmentFakeSmsMessage:
        now = as_utc(self.now_provider())
        message = DevelopmentFakeSmsMessage(
            message_id=secrets.token_urlsafe(24),
            phone_number=phone_number,
            code=code,
            delivery_type=delivery_type,
            created_at=now,
            available_at=now + timedelta(seconds=self.delivery_delay_seconds),
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        with self._lock:
            self._cleanup_locked(now)
            self._messages = [
                existing for existing in self._messages if existing.phone_number != phone_number
            ]
            self._messages.append(message)
            if len(self._messages) > self.max_messages:
                self._messages = self._messages[-self.max_messages :]
        return message

    def latest_available(self, phone_number: str) -> DevelopmentFakeSmsMessage | None:
        now = as_utc(self.now_provider())
        with self._lock:
            self._cleanup_locked(now)
            matches = [
                message
                for message in self._messages
                if message.phone_number == phone_number and message.available_at <= now
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

    def consume_code(self, phone_number: str, code: str) -> bool:
        now = as_utc(self.now_provider())
        with self._lock:
            self._cleanup_locked(now)
            before = len(self._messages)
            self._messages = [
                message
                for message in self._messages
                if not (message.phone_number == phone_number and message.code == code)
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

    def _cleanup_locked(self, now: datetime) -> None:
        self._messages = [message for message in self._messages if message.expires_at > now]


class DevelopmentFakeSmsSender:
    enabled = True
    available = True

    def __init__(self, store: DevelopmentFakeSmsStore) -> None:
        self.store = store

    def send_verification_code(
        self,
        phone_number: str,
        code: str,
        *,
        delivery_type: DeliveryType = "registration",
    ) -> SmsDeliveryResult:
        message = self.store.add(phone_number, code, delivery_type)
        return SmsDeliveryResult(
            delivered=True,
            provider="fake",
            request_id=message.message_id,
        )

    def consume_verification_code(self, phone_number: str, code: str) -> None:
        self.store.consume_code(phone_number, code)


development_fake_sms_store = DevelopmentFakeSmsStore(
    delivery_delay_seconds=settings.fake_sms_delivery_delay_seconds,
    ttl_seconds=settings.fake_sms_inbox_ttl_seconds,
    max_messages=settings.fake_sms_inbox_max_messages,
)
