from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.common.datetime_utils import as_utc
from app.common.enums import AccountStatus
from app.core.exceptions import InvalidPasswordChangeError
from app.core.security import hash_password, verify_password
from app.models.base import utc_now
from app.repositories.password_reset_code_repository import PasswordResetCodeRepository
from app.repositories.token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository

GENERIC_INVALID_PASSWORD_CHANGE_MESSAGE = "Password change could not be completed."
PASSWORD_CHANGE_SUCCESS_MESSAGE = (
    "Password changed successfully. Please sign in again."
)


@dataclass(frozen=True, slots=True)
class PasswordChangeResult:
    message: str = PASSWORD_CHANGE_SUCCESS_MESSAGE


class PasswordChangeService:
    """Atomically replace an authenticated user's password and recovery state."""

    def __init__(
        self,
        *,
        user_repository: UserRepository | None = None,
        reset_repository: PasswordResetCodeRepository | None = None,
        refresh_repository: RefreshTokenRepository | None = None,
        password_verifier: Callable[[str, str], bool] = verify_password,
        password_hasher: Callable[[str], str] = hash_password,
        now_provider: Callable[[], datetime] = utc_now,
    ) -> None:
        self.user_repository = user_repository or UserRepository()
        self.reset_repository = reset_repository or PasswordResetCodeRepository()
        self.refresh_repository = refresh_repository or RefreshTokenRepository()
        self.password_verifier = password_verifier
        self.password_hasher = password_hasher
        self.now_provider = now_provider

    def change_password(
        self,
        session: Session,
        *,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> PasswordChangeResult:
        now = as_utc(self.now_provider())

        with self._transaction(session):
            user = self.user_repository.get_by_id_for_update(session, user_id)
            if user is None or user.account_status is not AccountStatus.ACTIVE:
                raise InvalidPasswordChangeError

            current_hash = user.password_hash
            current_password_matches = self.password_verifier(
                current_password,
                current_hash,
            )
            new_password_matches = self.password_verifier(
                new_password,
                current_hash,
            )
            if not current_password_matches or new_password_matches:
                raise InvalidPasswordChangeError

            self.user_repository.update_password_hash(
                user,
                self.password_hasher(new_password),
            )
            self.reset_repository.invalidate_active_for_user(
                session,
                user_id=user.id,
                now=now,
            )
            self.refresh_repository.revoke_all_for_user(
                session,
                user_id=user.id,
                reason="logout_all",
                now=now,
            )

        return PasswordChangeResult()

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
