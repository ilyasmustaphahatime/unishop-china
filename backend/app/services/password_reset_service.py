from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.common.datetime_utils import as_utc
from app.common.enums import AccountStatus
from app.core.config import Settings, settings
from app.core.security import (
    VerificationCodeGenerator,
    generate_verification_code,
    hash_password_reset_code,
    resolve_verification_code_secret,
)
from app.integrations.password_reset_delivery import (
    PasswordResetDeliveryProvider,
    PasswordResetDestinationKind,
)
from app.models.base import utc_now
from app.models.password_reset_code import PasswordResetCode
from app.models.user import User
from app.repositories.password_reset_code_repository import PasswordResetCodeRepository
from app.repositories.user_repository import UserRepository

GENERIC_FORGOT_PASSWORD_MESSAGE = (
    "If an account matches that information, password reset instructions have been sent."
)
DUMMY_PASSWORD_RESET_USER_ID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True, slots=True)
class ForgotPasswordResult:
    message: str = GENERIC_FORGOT_PASSWORD_MESSAGE


class PasswordResetRequestService:
    def __init__(
        self,
        config: Settings = settings,
        *,
        delivery_provider: PasswordResetDeliveryProvider,
        user_repository: UserRepository | None = None,
        reset_repository: PasswordResetCodeRepository | None = None,
        code_generator: VerificationCodeGenerator = generate_verification_code,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.config = config
        self.delivery_provider = delivery_provider
        self.user_repository = user_repository or UserRepository()
        self.reset_repository = reset_repository or PasswordResetCodeRepository()
        self.code_generator = code_generator
        self.now_provider = now_provider

    def request_reset(
        self,
        session: Session,
        *,
        identifier: str,
        identifier_kind: PasswordResetDestinationKind,
    ) -> ForgotPasswordResult:
        now = as_utc(self.now_provider())
        secret = resolve_verification_code_secret(
            self.config.verification_code_hash_secret
        )
        raw_code = self.code_generator()
        code_hash = hash_password_reset_code(raw_code, secret)
        pending_code_id: str | None = None
        pending_user_id: str | None = None
        expires_at = now + timedelta(
            minutes=self.config.password_reset_code_expiry_minutes
        )

        with self._transaction(session):
            user = self._find_user_for_update(session, identifier, identifier_kind)
            eligible = (
                user is not None
                and user.account_status is AccountStatus.ACTIVE
                and self.delivery_provider.enabled
                and self.delivery_provider.available
            )
            workload_user_id = user.id if eligible else DUMMY_PASSWORD_RESET_USER_ID
            latest = self.reset_repository.get_latest_for_user(
                session,
                workload_user_id,
                for_update=True,
            )
            recent_count = self.reset_repository.count_created_since(
                session,
                user_id=workload_user_id,
                since=now - timedelta(hours=1),
            )

            if eligible and self._may_issue(now, latest, recent_count):
                self.reset_repository.invalidate_active_for_user(
                    session,
                    user_id=user.id,
                    now=now,
                )
                pending = self.reset_repository.create_pending(
                    session,
                    user_id=user.id,
                    code_hash=code_hash,
                    expires_at=expires_at,
                    pending_at=now,
                )
                pending_code_id = pending.id
                pending_user_id = user.id

        if pending_code_id is None or pending_user_id is None:
            return ForgotPasswordResult()

        try:
            delivery = self.delivery_provider.deliver_reset_code(
                identifier=identifier,
                identifier_kind=identifier_kind,
                code=raw_code,
                expires_at=expires_at,
            )
            if not delivery.delivered:
                return ForgotPasswordResult()
        except Exception:
            return ForgotPasswordResult()

        try:
            with self._transaction(session):
                user = self.user_repository.get_by_id_for_update(
                    session, pending_user_id
                )
                latest = self.reset_repository.get_latest_for_user(
                    session,
                    pending_user_id,
                    for_update=True,
                )
                if (
                    user is not None
                    and user.account_status is AccountStatus.ACTIVE
                    and latest is not None
                    and latest.id == pending_code_id
                ):
                    self.reset_repository.activate_pending(
                        session,
                        code_id=pending_code_id,
                    )
        except Exception:
            pass
        return ForgotPasswordResult()

    def _find_user_for_update(
        self,
        session: Session,
        identifier: str,
        identifier_kind: PasswordResetDestinationKind,
    ) -> User | None:
        if identifier_kind == "email":
            return self.user_repository.get_by_email(
                session,
                identifier,
                for_update=True,
            )
        return self.user_repository.get_by_phone(
            session,
            identifier,
            for_update=True,
        )

    def _may_issue(
        self,
        now: datetime,
        latest: PasswordResetCode | None,
        recent_count: int,
    ) -> bool:
        if recent_count >= self.config.password_reset_hourly_limit_requests:
            return False
        if latest is None:
            return True
        age_seconds = (now - as_utc(latest.created_at)).total_seconds()
        return age_seconds >= self.config.password_reset_cooldown_seconds

    @staticmethod
    @contextmanager
    def _transaction(session: Session) -> Iterator[None]:
        transaction = session.begin_nested() if session.in_transaction() else session.begin()
        with transaction:
            yield
