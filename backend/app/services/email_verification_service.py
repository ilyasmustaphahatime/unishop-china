from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus

from sqlalchemy.orm import Session

from app.common.datetime_utils import as_utc
from app.common.enums import AccountStatus
from app.core.config import Settings, settings
from app.core.exceptions import EmailVerificationError
from app.core.security import (
    VerificationCodeGenerator,
    generate_verification_code,
    hash_email_verification_code,
    resolve_verification_code_secret,
    verify_email_verification_code,
)
from app.integrations.email_verification_delivery import (
    EmailVerificationDeliveryProvider,
)
from app.models.base import utc_now
from app.repositories.email_verification_code_repository import (
    EmailVerificationCodeRepository,
)
from app.repositories.user_repository import UserRepository

GENERIC_EMAIL_RESEND_MESSAGE = (
    "If this account is eligible, an email verification code will be sent."
)
GENERIC_INVALID_EMAIL_VERIFICATION_MESSAGE = (
    "Invalid or expired email verification request."
)
EMAIL_VERIFIED_MESSAGE = "Email address verified successfully."
DUMMY_EMAIL_VERIFICATION_CODE_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class EmailVerificationResendResult:
    message: str = GENERIC_EMAIL_RESEND_MESSAGE
    expires_in_seconds: int = 600


@dataclass(frozen=True, slots=True)
class EmailVerificationResult:
    message: str = EMAIL_VERIFIED_MESSAGE
    email_verified: bool = True


class EmailVerificationService:
    """Own authenticated email challenge delivery and atomic verification."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        delivery_provider: EmailVerificationDeliveryProvider,
        user_repository: UserRepository | None = None,
        challenge_repository: EmailVerificationCodeRepository | None = None,
        code_generator: VerificationCodeGenerator = generate_verification_code,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.config = config
        self.delivery_provider = delivery_provider
        self.user_repository = user_repository or UserRepository()
        self.challenge_repository = (
            challenge_repository or EmailVerificationCodeRepository()
        )
        self.code_generator = code_generator
        self.now_provider = now_provider

    def resend(self, session: Session, *, user_id: str) -> EmailVerificationResendResult:
        now = as_utc(self.now_provider())
        expires_at = now + timedelta(
            minutes=self.config.email_verification_code_expiry_minutes
        )
        pending_code_id: str | None = None
        raw_code: str | None = None
        destination: str | None = None

        with self._transaction(session):
            user = self.user_repository.get_by_id_for_update(session, user_id)
            if not self._eligible(user):
                return self._resend_result()
            if not self.delivery_provider.enabled or not self.delivery_provider.available:
                raise self._provider_error()

            latest = self.challenge_repository.get_latest_created_for_user(
                session,
                user.id,
                for_update=True,
            )
            if latest is not None:
                age_seconds = (now - as_utc(latest.created_at)).total_seconds()
                if age_seconds < self.config.email_verification_cooldown_seconds:
                    retry_after = max(
                        1,
                        self.config.email_verification_cooldown_seconds
                        - max(0, int(age_seconds)),
                    )
                    raise self._rate_limit_error(retry_after)

            recent_count = self.challenge_repository.count_created_since(
                session,
                user_id=user.id,
                since=now - timedelta(hours=1),
            )
            if recent_count >= self.config.email_verification_hourly_limit_requests:
                oldest = self.challenge_repository.get_oldest_created_since(
                    session,
                    user_id=user.id,
                    since=now - timedelta(hours=1),
                )
                retry_after = 3600
                if oldest is not None:
                    retry_after = max(
                        1,
                        3600 - max(0, int((now - as_utc(oldest)).total_seconds())),
                    )
                raise self._rate_limit_error(retry_after)

            raw_code = self.code_generator()
            if not self._valid_generated_code(raw_code):
                raise RuntimeError("Email verification code generator returned invalid output.")
            secret = resolve_verification_code_secret(
                self.config.verification_code_hash_secret
            )
            pending = self.challenge_repository.create_pending(
                session,
                user_id=user.id,
                code_hash=hash_email_verification_code(raw_code, secret),
                expires_at=expires_at,
                created_at=now,
            )
            pending_code_id = pending.id
            destination = user.email

        assert pending_code_id is not None
        assert raw_code is not None
        assert destination is not None

        try:
            delivery = self.delivery_provider.deliver_verification_code(
                user_id=user_id,
                email=destination,
                code=raw_code,
                expires_at=expires_at,
            )
            if not delivery.delivered:
                raise RuntimeError("Email provider did not confirm delivery.")
        except Exception as exc:
            self._cancel_pending(session, pending_code_id, user_id, now)
            self._consume_provider_code(user_id, raw_code)
            raise self._provider_error() from exc

        activated = False
        try:
            with self._transaction(session):
                user = self.user_repository.get_by_id_for_update(session, user_id)
                latest = self.challenge_repository.get_latest_created_for_user(
                    session,
                    user_id,
                    for_update=True,
                )
                if (
                    self._eligible(user)
                    and user.email == destination
                    and latest is not None
                    and latest.id == pending_code_id
                ):
                    activated = (
                        self.challenge_repository.activate_pending(
                            session,
                            code_id=pending_code_id,
                            user_id=user_id,
                            now=now,
                        )
                        == 1
                    )
                    if activated:
                        self.challenge_repository.invalidate_active_for_user(
                            session,
                            user_id=user_id,
                            now=now,
                            exclude_code_id=pending_code_id,
                        )
                if not activated:
                    self.challenge_repository.cancel_pending(
                        session,
                        code_id=pending_code_id,
                        user_id=user_id,
                        now=now,
                    )
        except Exception:
            self._cancel_pending(session, pending_code_id, user_id, now)
            self._consume_provider_code(user_id, raw_code)
            raise self._provider_error()

        if not activated:
            self._consume_provider_code(user_id, raw_code)
        return self._resend_result()

    def verify(
        self,
        session: Session,
        *,
        user_id: str,
        submitted_code: str,
    ) -> EmailVerificationResult:
        now = as_utc(self.now_provider())
        succeeded = False

        with self._transaction(session):
            user = self.user_repository.get_by_id_for_update(session, user_id)
            eligible = self._eligible(user)
            challenge = self.challenge_repository.get_latest_active_for_user(
                session,
                user_id,
                for_update=True,
            )
            stored_hash = (
                challenge.code_hash
                if eligible and challenge is not None
                else DUMMY_EMAIL_VERIFICATION_CODE_HASH
            )
            secret = resolve_verification_code_secret(
                self.config.verification_code_hash_secret
            )
            code_matches = verify_email_verification_code(
                submitted_code,
                stored_hash,
                secret,
            )
            challenge_available = (
                eligible
                and challenge is not None
                and challenge.activated_at is not None
                and challenge.used_at is None
                and as_utc(challenge.expires_at) > now
                and challenge.attempts < self.config.email_verification_max_attempts
            )

            if challenge_available and not code_matches:
                self.challenge_repository.increment_attempts_if_available(
                    session,
                    code_id=challenge.id,
                    user_id=user_id,
                    now=now,
                    maximum_attempts=self.config.email_verification_max_attempts,
                )
            elif challenge_available and code_matches:
                consumed = self.challenge_repository.consume_if_available(
                    session,
                    code_id=challenge.id,
                    user_id=user_id,
                    now=now,
                    maximum_attempts=self.config.email_verification_max_attempts,
                )
                if consumed != 1:
                    raise RuntimeError("Email verification challenge could not be consumed.")
                self.user_repository.mark_email_verified(user)
                self.challenge_repository.invalidate_active_for_user(
                    session,
                    user_id=user_id,
                    now=now,
                    exclude_code_id=challenge.id,
                )
                succeeded = True

        if not succeeded:
            raise self._invalid_error()
        self._consume_provider_code(user_id, submitted_code)
        return EmailVerificationResult()

    def _cancel_pending(
        self,
        session: Session,
        code_id: str,
        user_id: str,
        now: datetime,
    ) -> None:
        try:
            with self._transaction(session):
                self.user_repository.get_by_id_for_update(session, user_id)
                self.challenge_repository.cancel_pending(
                    session,
                    code_id=code_id,
                    user_id=user_id,
                    now=now,
                )
        except Exception:
            session.rollback()

    def _consume_provider_code(self, user_id: str, code: str) -> None:
        try:
            self.delivery_provider.consume_verification_code(
                user_id=user_id,
                code=code,
            )
        except Exception:
            pass

    def _resend_result(self) -> EmailVerificationResendResult:
        return EmailVerificationResendResult(
            expires_in_seconds=self.config.email_verification_code_expiry_minutes * 60
        )

    @staticmethod
    def _eligible(user: object) -> bool:
        return bool(
            user is not None
            and user.account_status is AccountStatus.ACTIVE
            and user.email
            and not user.email_verified
        )

    @staticmethod
    def _valid_generated_code(code: object) -> bool:
        return (
            isinstance(code, str)
            and len(code) == 6
            and code.isascii()
            and code.isdigit()
        )

    @staticmethod
    def _invalid_error() -> EmailVerificationError:
        return EmailVerificationError(
            "EMAIL_VERIFICATION_INVALID",
            GENERIC_INVALID_EMAIL_VERIFICATION_MESSAGE,
            HTTPStatus.BAD_REQUEST,
        )

    @staticmethod
    def _provider_error() -> EmailVerificationError:
        return EmailVerificationError(
            "EMAIL_VERIFICATION_UNAVAILABLE",
            "Email verification delivery is temporarily unavailable.",
            HTTPStatus.SERVICE_UNAVAILABLE,
        )

    @staticmethod
    def _rate_limit_error(retry_after: int | None) -> EmailVerificationError:
        return EmailVerificationError(
            "EMAIL_VERIFICATION_RATE_LIMITED",
            "Too many email verification requests. Please try again later.",
            HTTPStatus.TOO_MANY_REQUESTS,
            retry_after=retry_after,
        )

    @staticmethod
    @contextmanager
    def _transaction(session: Session) -> Iterator[None]:
        if session.in_transaction():
            with session.begin_nested():
                yield
            session.commit()
            return
        with session.begin():
            yield
