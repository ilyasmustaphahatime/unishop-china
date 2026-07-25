from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Callable

from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.common.datetime_utils import as_utc
from app.core.exceptions import PhoneVerificationError
from app.core.security import (
    VerificationCodeGenerator,
    generate_verification_code,
    hash_verification_code,
    resolve_verification_code_secret,
    verify_verification_code,
)
from app.integrations.sms_client import SmsSender
from app.models.base import utc_now
from app.repositories.phone_verification_code_repository import (
    PhoneVerificationCodeRepository,
)
from app.repositories.user_repository import UserRepository

GENERIC_RESEND_MESSAGE = "If this phone number is eligible, a verification code will be sent."
VERIFIED_MESSAGE = "Phone number verified successfully."
INVALID_MESSAGE = "The verification code is invalid."


@dataclass(frozen=True, slots=True)
class ResendResult:
    message: str = GENERIC_RESEND_MESSAGE
    expires_in_seconds: int = 600


@dataclass(frozen=True, slots=True)
class VerificationResult:
    message: str = VERIFIED_MESSAGE
    phone_verified: bool = True


class PhoneVerificationService:
    def __init__(
        self,
        *,
        sms_sender: SmsSender,
        verification_code_hash_secret: SecretStr | str | None,
        user_repository: UserRepository | None = None,
        phone_code_repository: PhoneVerificationCodeRepository | None = None,
        verification_code_generator: VerificationCodeGenerator = generate_verification_code,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.sms_sender = sms_sender
        self.verification_code_hash_secret = verification_code_hash_secret
        self.user_repository = user_repository or UserRepository()
        self.phone_code_repository = phone_code_repository or PhoneVerificationCodeRepository()
        self.verification_code_generator = verification_code_generator
        self.now_provider = now_provider

    def resend(self, session: Session, phone_number: str) -> ResendResult:
        if not self.sms_sender.enabled:
            return ResendResult()
        if not self.sms_sender.available:
            self._provider_unavailable()

        raw_code: str | None = None
        code_id: str | None = None
        now = as_utc(self.now_provider())
        with session.begin():
            user = self.user_repository.get_by_phone(session, phone_number, for_update=True)
            if user is None or user.phone_verified:
                return ResendResult()

            latest = self.phone_code_repository.get_latest_for_phone(session, phone_number)
            if latest is not None:
                age = (now - as_utc(latest.created_at)).total_seconds()
                if age < 60:
                    retry_after = max(1, 60 - int(age))
                    raise PhoneVerificationError(
                        "VERIFICATION_CODE_RATE_LIMITED",
                        "Please wait before requesting another verification code.",
                        HTTPStatus.TOO_MANY_REQUESTS,
                        retry_after=retry_after,
                    )

            if (
                self.phone_code_repository.count_created_since(
                    session, phone_number, now - timedelta(hours=1)
                )
                >= 5
            ):
                raise PhoneVerificationError(
                    "VERIFICATION_CODE_RATE_LIMITED",
                    "Too many verification codes have been requested. Please try again later.",
                    HTTPStatus.TOO_MANY_REQUESTS,
                )

            secret = resolve_verification_code_secret(self.verification_code_hash_secret)
            raw_code = self.verification_code_generator()
            record = self.phone_code_repository.create_code(
                session,
                user_id=user.id,
                phone_number=phone_number,
                code_hash=hash_verification_code(raw_code, secret),
                expires_at=now + timedelta(minutes=10),
            )
            code_id = record.id

        try:
            result = self.sms_sender.send_verification_code(
                phone_number,
                raw_code,
                delivery_type="resend",
            )
            if not result.delivered:
                raise RuntimeError("SMS provider did not confirm delivery.")
        except Exception as exc:
            self._expire_unsent_code(session, code_id)
            raise PhoneVerificationError(
                "SMS_PROVIDER_UNAVAILABLE",
                "SMS delivery is temporarily unavailable. Please try again later.",
                HTTPStatus.SERVICE_UNAVAILABLE,
            ) from exc
        return ResendResult()

    def verify(
        self, session: Session, phone_number: str, submitted_code: str
    ) -> VerificationResult:
        outcome: PhoneVerificationError | None = None
        verified = False
        now = as_utc(self.now_provider())
        with session.begin():
            user = self.user_repository.get_by_phone(session, phone_number, for_update=True)
            if user is None:
                outcome = self._invalid_error()
            elif user.phone_verified:
                return VerificationResult()
            else:
                code = self.phone_code_repository.get_latest_for_user(
                    session, user.id, for_update=True
                )
                if code is None or code.verified_at is not None:
                    outcome = self._invalid_error()
                elif now >= as_utc(code.expires_at):
                    outcome = PhoneVerificationError(
                        "VERIFICATION_CODE_EXPIRED",
                        "The verification code has expired.",
                        HTTPStatus.GONE,
                    )
                elif code.attempts >= 5:
                    outcome = self._attempts_error()
                else:
                    secret = resolve_verification_code_secret(self.verification_code_hash_secret)
                    if verify_verification_code(submitted_code, code.code_hash, secret):
                        self.user_repository.mark_phone_verified(user)
                        self.phone_code_repository.mark_verified(code, now)
                        verified = True
                    else:
                        attempts = self.phone_code_repository.increment_attempts(session, code.id)
                        outcome = self._attempts_error() if attempts >= 5 else self._invalid_error()

        if outcome is not None:
            raise outcome
        if verified:
            try:
                self.sms_sender.consume_verification_code(phone_number, submitted_code)
            except Exception:
                pass
        return VerificationResult()

    def _expire_unsent_code(self, session: Session, code_id: str | None) -> None:
        if code_id is None:
            return
        try:
            with session.begin():
                record = self.phone_code_repository.get_by_id(session, code_id)
                if record is not None:
                    self.phone_code_repository.expire_code(
                        record, as_utc(self.now_provider()) - timedelta(seconds=1)
                    )
        except Exception:
            session.rollback()

    @staticmethod
    def _invalid_error() -> PhoneVerificationError:
        return PhoneVerificationError(
            "INVALID_VERIFICATION_CODE", INVALID_MESSAGE, HTTPStatus.BAD_REQUEST
        )

    @staticmethod
    def _attempts_error() -> PhoneVerificationError:
        return PhoneVerificationError(
            "VERIFICATION_ATTEMPTS_EXCEEDED",
            "The maximum number of verification attempts has been reached.",
            HTTPStatus.TOO_MANY_REQUESTS,
        )

    @staticmethod
    def _provider_unavailable() -> None:
        raise PhoneVerificationError(
            "SMS_PROVIDER_UNAVAILABLE",
            "SMS delivery is temporarily unavailable. Please try again later.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )
