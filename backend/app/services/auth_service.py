from collections.abc import Callable
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets

from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus, UserRoleType
from app.core.exceptions import InvalidCredentialsError, RegistrationConflictError
from app.core.security import (
    VerificationCodeGenerator,
    generate_verification_code,
    hash_password,
    hash_verification_code,
    resolve_verification_code_secret,
    verify_password,
)
from app.models.base import utc_now
from app.integrations.sms_client import DisabledSmsSender, SmsSender
from app.repositories.phone_verification_code_repository import (
    PhoneVerificationCodeRepository,
)
from app.repositories.role_repository import UserRoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.token_service import AccessTokenService
from app.services.refresh_session_service import AuthCookieMaterial, RefreshSessionService


_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


@dataclass(frozen=True, slots=True)
class RegistrationResult:
    id: str
    email: str | None
    phone_number: str | None
    phone_verified: bool
    email_verified: bool
    account_status: AccountStatus
    roles: list[UserRoleType]
    phone_verification_required: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SafeAuthenticatedUser:
    id: str
    email: str | None
    phone_number: str | None
    email_verified: bool
    phone_verified: bool
    account_status: AccountStatus
    roles: list[UserRoleType]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    access_token: str
    token_type: str
    expires_in: int
    user: SafeAuthenticatedUser
    cookies: AuthCookieMaterial


class AuthenticationService:
    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        role_repository: UserRoleRepository | None = None,
        token_service: AccessTokenService | None = None,
        refresh_session_service: RefreshSessionService | None = None,
        password_verifier: Callable[[str, str], bool] = verify_password,
        dummy_password_hash: str = _DUMMY_PASSWORD_HASH,
    ) -> None:
        self.user_repository = user_repository or UserRepository()
        self.role_repository = role_repository or UserRoleRepository()
        self.token_service = token_service or AccessTokenService()
        self.refresh_session_service = refresh_session_service or RefreshSessionService(
            access_token_service=self.token_service
        )
        self.password_verifier = password_verifier
        self.dummy_password_hash = dummy_password_hash

    def authenticate_user_and_create_access_token(
        self,
        session: Session,
        request: LoginRequest,
    ) -> AuthenticationResult:
        with self._transaction(session):
            if request.identifier_kind == "email":
                user = self.user_repository.get_by_email(session, request.identifier)
            else:
                user = self.user_repository.get_by_phone(session, request.identifier)

            password_hash = user.password_hash if user is not None else self.dummy_password_hash
            password_is_valid = self.password_verifier(request.password, password_hash)
            if (
                user is None
                or not password_is_valid
                or user.account_status is not AccountStatus.ACTIVE
            ):
                raise InvalidCredentialsError

            safe_user = self._safe_user(session, user)
            cookies = self.refresh_session_service.create_login_session(
                session,
                user_id=user.id,
            )
            return AuthenticationResult(
                access_token=self.token_service.create_access_token(user.id),
                token_type="bearer",
                expires_in=self.token_service.expires_in_seconds,
                user=safe_user,
                cookies=cookies,
            )

    def load_current_user(self, session: Session, user_id: str) -> SafeAuthenticatedUser | None:
        user = self.user_repository.get_by_id(session, user_id)
        if user is None or user.account_status is not AccountStatus.ACTIVE:
            return None
        return self._safe_user(session, user)

    def _safe_user(self, session: Session, user: object) -> SafeAuthenticatedUser:
        roles = self.role_repository.list_roles_for_user(session, user.id)
        return SafeAuthenticatedUser(
            id=user.id,
            email=user.email,
            phone_number=user.phone_number,
            email_verified=user.email_verified,
            phone_verified=user.phone_verified,
            account_status=user.account_status,
            roles=roles,
            created_at=user.created_at,
        )

    @staticmethod
    @contextmanager
    def _transaction(session: Session) -> Iterator[None]:
        transaction = session.begin_nested() if session.in_transaction() else session.begin()
        with transaction:
            yield


class RegistrationService:
    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        role_repository: UserRoleRepository | None = None,
        phone_code_repository: PhoneVerificationCodeRepository | None = None,
        verification_code_hash_secret: SecretStr | str | None = None,
        verification_code_generator: VerificationCodeGenerator = generate_verification_code,
        sms_sender: SmsSender | None = None,
    ) -> None:
        self.user_repository = user_repository or UserRepository()
        self.role_repository = role_repository or UserRoleRepository()
        self.phone_code_repository = phone_code_repository or PhoneVerificationCodeRepository()
        self.verification_code_hash_secret = verification_code_hash_secret
        self.verification_code_generator = verification_code_generator
        self.sms_sender = sms_sender or DisabledSmsSender()

    def register(self, session: Session, request: RegisterRequest) -> RegistrationResult:
        raw_code: str | None = None
        code_id: str | None = None
        try:
            with session.begin():
                self._check_duplicates(session, request)
                password_digest = hash_password(request.password)
                user = self.user_repository.create(
                    session,
                    email=str(request.email) if request.email is not None else None,
                    phone_number=request.phone_number,
                    password_hash=password_digest,
                )
                self.role_repository.create_role(
                    session,
                    user_id=user.id,
                    role=UserRoleType.BUYER,
                )

                if request.phone_number is not None:
                    secret = resolve_verification_code_secret(self.verification_code_hash_secret)
                    raw_code = self.verification_code_generator()
                    code_hash = hash_verification_code(raw_code, secret)
                    record = self.phone_code_repository.create_code(
                        session,
                        user_id=user.id,
                        phone_number=request.phone_number,
                        code_hash=code_hash,
                        expires_at=utc_now() + timedelta(minutes=10),
                    )
                    code_id = record.id

                result = RegistrationResult(
                    id=user.id,
                    email=user.email,
                    phone_number=user.phone_number,
                    phone_verified=user.phone_verified,
                    email_verified=user.email_verified,
                    account_status=user.account_status,
                    roles=[UserRoleType.BUYER],
                    phone_verification_required=user.phone_number is not None,
                    created_at=user.created_at,
                )
        except RegistrationConflictError:
            raise
        except IntegrityError as exc:
            session.rollback()
            raise self._safe_integrity_conflict(exc) from exc

        if request.phone_number is not None and raw_code is not None:
            try:
                delivery = self.sms_sender.send_verification_code(
                    request.phone_number,
                    raw_code,
                    delivery_type="registration",
                )
                if not delivery.delivered:
                    self._expire_unsent_code(session, code_id)
            except Exception:
                self._expire_unsent_code(session, code_id)

        return result

    def _expire_unsent_code(self, session: Session, code_id: str | None) -> None:
        if code_id is None:
            return
        try:
            with session.begin():
                record = self.phone_code_repository.get_by_id(session, code_id)
                if record is not None:
                    self.phone_code_repository.expire_code(record, utc_now() - timedelta(seconds=1))
        except Exception:
            session.rollback()

    def _check_duplicates(self, session: Session, request: RegisterRequest) -> None:
        if request.email is not None and self.user_repository.get_by_email(
            session, str(request.email)
        ):
            raise RegistrationConflictError(
                "EMAIL_ALREADY_REGISTERED",
                "An account with this email already exists.",
            )
        if request.phone_number is not None and self.user_repository.get_by_phone(
            session, request.phone_number
        ):
            raise RegistrationConflictError(
                "PHONE_ALREADY_REGISTERED",
                "An account with this phone number already exists.",
            )

    @staticmethod
    def _safe_integrity_conflict(error: IntegrityError) -> RegistrationConflictError:
        database_message = str(getattr(error, "orig", "")).lower()
        if "ix_users_email" in database_message:
            return RegistrationConflictError(
                "EMAIL_ALREADY_REGISTERED",
                "An account with this email already exists.",
            )
        if "ix_users_phone_number" in database_message:
            return RegistrationConflictError(
                "PHONE_ALREADY_REGISTERED",
                "An account with this phone number already exists.",
            )
        return RegistrationConflictError(
            "REGISTRATION_CONFLICT",
            "Registration could not be completed because the account conflicts with existing data.",
        )
