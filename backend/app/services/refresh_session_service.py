from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.datetime_utils import as_utc
from app.common.enums import AccountStatus
from app.core.config import Settings, settings, validate_session_configuration
from app.core.exceptions import RefreshTokenCollisionError, SessionRefreshError
from app.core.session_security import (
    generate_csrf_token,
    generate_refresh_token,
    hash_csrf_token,
    hash_refresh_token,
    validate_csrf_tokens,
)
from app.models.base import utc_now
from app.models.refresh_token import RefreshToken
from app.repositories.token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.token_service import AccessTokenService


@dataclass(frozen=True, slots=True)
class AuthCookieMaterial:
    refresh_token: str
    csrf_token: str
    max_age: int


@dataclass(frozen=True, slots=True)
class RefreshAccessResult:
    access_token: str
    token_type: str
    expires_in: int
    cookies: AuthCookieMaterial


class RefreshSessionService:
    """Own refresh-session creation, rotation, revocation, and transactions."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        repository: RefreshTokenRepository | None = None,
        user_repository: UserRepository | None = None,
        access_token_service: AccessTokenService | None = None,
        now_provider: Callable[[], datetime] = utc_now,
        refresh_token_generator: Callable[[], str] = generate_refresh_token,
        csrf_token_generator: Callable[[], str] = generate_csrf_token,
        family_id_generator: Callable[[], str] = lambda: str(uuid4()),
        collision_attempts: int = 3,
    ) -> None:
        validate_session_configuration(config)
        if collision_attempts < 1 or collision_attempts > 10:
            raise ValueError("Refresh-token collision attempts must be between 1 and 10.")
        self.config = config
        self.repository = repository or RefreshTokenRepository()
        self.user_repository = user_repository or UserRepository()
        self.access_token_service = access_token_service or AccessTokenService(config)
        self.now_provider = now_provider
        self.refresh_token_generator = refresh_token_generator
        self.csrf_token_generator = csrf_token_generator
        self.family_id_generator = family_id_generator
        self.collision_attempts = collision_attempts
        self.refresh_lifetime = timedelta(days=config.refresh_token_expire_days)
        self.absolute_lifetime = timedelta(days=config.refresh_session_absolute_days)

    def create_login_session(self, session: Session, *, user_id: str) -> AuthCookieMaterial:
        """Create a new family inside the caller-owned successful-login transaction."""
        now = as_utc(self.now_provider())
        user = self.user_repository.get_by_id_for_update(session, user_id)
        if user is None or user.account_status is not AccountStatus.ACTIVE:
            raise SessionRefreshError

        active_count = self.repository.count_active_families(
            session,
            user_id=user_id,
            now=now,
        )
        families_to_revoke = max(
            0,
            active_count - self.config.max_active_session_families_per_user + 1,
        )
        for _ in range(families_to_revoke):
            oldest = self.repository.get_oldest_active_family(
                session,
                user_id=user_id,
                now=now,
            )
            if oldest is None:
                break
            self.repository.revoke_family(
                session,
                family_id=oldest,
                reason="session_limit",
                now=now,
            )

        family_expires_at = now + self.absolute_lifetime
        _, material = self._create_token_record(
            session,
            user_id=user_id,
            family_id=self.family_id_generator(),
            family_expires_at=family_expires_at,
            now=now,
        )
        return material

    def rotate_session(
        self,
        session: Session,
        *,
        raw_refresh_token: str,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> RefreshAccessResult:
        if not raw_refresh_token:
            raise SessionRefreshError
        validate_csrf_tokens(cookie_token=csrf_cookie, header_token=csrf_header)
        presented_hash = hash_refresh_token(raw_refresh_token)
        material: AuthCookieMaterial | None = None
        user_id: str | None = None
        invalid_session = False

        with self._transaction(session):
            current = self.repository.get_for_update_by_hash(session, presented_hash)
            if current is None:
                invalid_session = True
            else:
                validate_csrf_tokens(
                    cookie_token=csrf_cookie,
                    header_token=csrf_header,
                    stored_hash=current.csrf_token_hash,
                )
                now = as_utc(self.now_provider())
                if current.revoked_at is not None:
                    self.repository.revoke_family(
                        session,
                        family_id=current.family_id,
                        reason="reuse_detected",
                        now=now,
                        include_revoked=True,
                    )
                    invalid_session = True
                elif (
                    as_utc(current.expires_at) <= now
                    or as_utc(current.family_expires_at) <= now
                ):
                    self.repository.revoke_family(
                        session,
                        family_id=current.family_id,
                        reason="expired_cleanup",
                        now=now,
                    )
                    invalid_session = True
                else:
                    user = self.user_repository.get_by_id_for_update(session, current.user_id)
                    if user is None or user.account_status is not AccountStatus.ACTIVE:
                        self.repository.revoke_family(
                            session,
                            family_id=current.family_id,
                            reason="inactive_account",
                            now=now,
                        )
                        invalid_session = True
                    else:
                        replacement, material = self._create_token_record(
                            session,
                            user_id=current.user_id,
                            family_id=current.family_id,
                            family_expires_at=as_utc(current.family_expires_at),
                            now=now,
                        )
                        self.repository.mark_token_rotated(
                            current,
                            replacement_id=replacement.id,
                            now=now,
                        )
                        user_id = current.user_id

        if invalid_session or material is None or user_id is None:
            raise SessionRefreshError
        return RefreshAccessResult(
            access_token=self.access_token_service.create_access_token(user_id),
            token_type="bearer",
            expires_in=self.access_token_service.expires_in_seconds,
            cookies=material,
        )

    def logout_current(
        self,
        session: Session,
        *,
        raw_refresh_token: str | None,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> None:
        if not raw_refresh_token:
            return
        validate_csrf_tokens(cookie_token=csrf_cookie, header_token=csrf_header)
        token_hash = hash_refresh_token(raw_refresh_token)
        with self._transaction(session):
            current = self.repository.get_for_update_by_hash(session, token_hash)
            if current is None:
                return
            validate_csrf_tokens(
                cookie_token=csrf_cookie,
                header_token=csrf_header,
                stored_hash=current.csrf_token_hash,
            )
            if current.revoked_at is None:
                self.repository.revoke_family(
                    session,
                    family_id=current.family_id,
                    reason="logout",
                    now=as_utc(self.now_provider()),
                )

    def logout_all(self, session: Session, *, user_id: str) -> None:
        with self._transaction(session):
            self.repository.revoke_all_for_user(
                session,
                user_id=user_id,
                reason="logout_all",
                now=as_utc(self.now_provider()),
            )

    def _create_token_record(
        self,
        session: Session,
        *,
        user_id: str,
        family_id: str,
        family_expires_at: datetime,
        now: datetime,
    ) -> tuple[RefreshToken, AuthCookieMaterial]:
        expires_at = min(now + self.refresh_lifetime, family_expires_at)
        if expires_at <= now:
            raise SessionRefreshError

        for _ in range(self.collision_attempts):
            raw_refresh_token = self.refresh_token_generator()
            token_hash = hash_refresh_token(raw_refresh_token)
            if self.repository.token_hash_exists(session, token_hash):
                continue
            csrf_token = self.csrf_token_generator()
            try:
                with session.begin_nested():
                    record = self.repository.create_refresh_session(
                        session,
                        user_id=user_id,
                        token_hash=token_hash,
                        family_id=family_id,
                        csrf_token_hash=hash_csrf_token(csrf_token),
                        expires_at=expires_at,
                        family_expires_at=family_expires_at,
                    )
            except IntegrityError:
                continue
            max_age = max(1, int((expires_at - now).total_seconds()))
            return record, AuthCookieMaterial(raw_refresh_token, csrf_token, max_age)
        raise RefreshTokenCollisionError

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
