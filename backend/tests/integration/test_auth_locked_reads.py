"""Locked authentication reads must replace an existing stale ORM identity."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.models import (
    EmailVerificationCode, PasswordResetCode, PhoneVerificationCode, RefreshToken, User,
)
from app.models.base import utc_now
from app.repositories.email_verification_code_repository import EmailVerificationCodeRepository
from app.repositories.password_reset_code_repository import PasswordResetCodeRepository
from app.repositories.phone_verification_code_repository import PhoneVerificationCodeRepository
from app.repositories.token_repository import RefreshTokenRepository


@pytest.mark.parametrize("lookup", ["refresh", "phone_user", "phone_number", "reset", "email_created", "email_active"])
def test_locked_auth_read_refreshes_cached_database_state(db_session, lookup):
    now = utc_now()
    user = User(email=f"locked-read-{uuid4().hex}@example.test", password_hash="unusable")
    db_session.add(user)
    db_session.flush()
    common = {"user_id": user.id, "expires_at": now + timedelta(minutes=10)}
    if lookup == "refresh":
        row = RefreshToken(**common, token_hash=uuid4().hex, family_id=str(uuid4()),
                           csrf_token_hash="0" * 64, family_expires_at=now + timedelta(days=1))
        def read():
            return RefreshTokenRepository().get_for_update_by_hash(db_session, row.token_hash)
        changed = "revocation_reason"
        value = "logout"
        values = {changed: value, "revoked_at": now}
    elif lookup.startswith("phone"):
        row = PhoneVerificationCode(**common, phone_number=f"+86138{uuid4().int % 100_000_000:08d}",
                                    code_hash="unusable")
        repo = PhoneVerificationCodeRepository()
        def read():
            if lookup == "phone_user":
                return repo.get_latest_for_user(db_session, user.id, for_update=True)
            return repo.get_latest_for_phone(db_session, row.phone_number, for_update=True)
        changed, value = "attempts", 5
        values = {changed: value}
    elif lookup == "reset":
        row = PasswordResetCode(**common, code_hash="unusable")
        def read():
            return PasswordResetCodeRepository().get_latest_for_user(db_session, user.id, for_update=True)
        changed, value = "attempts", 5
        values = {changed: value}
    else:
        row = EmailVerificationCode(**common, code_hash="0" * 64, activated_at=now)
        repo = EmailVerificationCodeRepository()
        def read():
            if lookup == "email_created":
                return repo.get_latest_created_for_user(db_session, user.id, for_update=True)
            return repo.get_latest_active_for_user(db_session, user.id, for_update=True)
        changed, value = "attempts", 5
        values = {changed: value}
    db_session.add(row)
    db_session.flush()
    model = type(row)
    assert db_session.scalar(select(model).where(model.id == row.id)) is row
    # Simulate a database-side change while retaining the previously loaded identity.
    # No external commits or pre-existing records are needed for this regression.
    db_session.execute(update(model).where(model.id == row.id).values(**values)
                       .execution_options(synchronize_session=False))
    assert db_session.scalar(select(getattr(model, changed)).where(model.id == row.id)) == value
    assert getattr(row, changed) != value
    current = read()
    assert current is row
    assert getattr(current, changed) == value
