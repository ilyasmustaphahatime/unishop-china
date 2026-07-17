from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus, UserRoleType
from app.models import (
    PasswordResetCode,
    PhoneVerificationCode,
    RefreshToken,
    User,
    UserRole,
)
from app.models.base import utc_now


def create_user(db_session: Session, suffix: str) -> User:
    user = User(email=f"{suffix}@example.test", password_hash=f"hash-{suffix}")
    db_session.add(user)
    db_session.flush()
    return user


def assert_foreign_key_rejected(db_session: Session, record: object) -> None:
    db_session.add(record)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize(
    ("email", "phone_number"),
    [
        ("email-only@example.test", None),
        (None, "+8613800000001"),
        ("both@example.test", "+8613800000002"),
    ],
)
def test_user_can_be_created_with_supported_identifiers(
    db_session: Session,
    email: str | None,
    phone_number: str | None,
) -> None:
    user = User(email=email, phone_number=phone_number, password_hash="secure-password-hash")
    db_session.add(user)
    db_session.flush()

    assert user.id is not None
    assert user.password_hash == "secure-password-hash"


def test_user_with_no_identifier_is_rejected(db_session: Session) -> None:
    db_session.add(User(password_hash="secure-password-hash"))

    with pytest.raises(DBAPIError):
        db_session.flush()


def test_duplicate_email_is_rejected(db_session: Session) -> None:
    db_session.add_all(
        [
            User(email="duplicate@example.test", password_hash="hash-one"),
            User(email="duplicate@example.test", password_hash="hash-two"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_phone_number_is_rejected(db_session: Session) -> None:
    db_session.add_all(
        [
            User(phone_number="+8613800000010", password_hash="hash-one"),
            User(phone_number="+8613800000010", password_hash="hash-two"),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_user_defaults_and_secure_columns(db_session: Session) -> None:
    user = create_user(db_session, "defaults")
    columns = set(User.__table__.columns.keys())

    assert user.account_status is AccountStatus.ACTIVE
    assert user.phone_verified is False
    assert user.email_verified is False
    assert "password_hash" in columns
    assert "password" not in columns
    assert "raw_password" not in columns


def test_buyer_and_seller_roles_can_share_a_user(db_session: Session) -> None:
    user = create_user(db_session, "multiple-roles")
    user.roles.extend(
        [
            UserRole(role=UserRoleType.BUYER),
            UserRole(role=UserRoleType.SELLER),
        ]
    )
    db_session.flush()

    assert {role.role for role in user.roles} == {UserRoleType.BUYER, UserRoleType.SELLER}


def test_duplicate_role_for_user_is_rejected(db_session: Session) -> None:
    user = create_user(db_session, "duplicate-role")
    db_session.add_all(
        [
            UserRole(user_id=user.id, role=UserRoleType.BUYER),
            UserRole(user_id=user.id, role=UserRoleType.BUYER),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_role_requires_existing_user(db_session: Session) -> None:
    assert_foreign_key_rejected(
        db_session,
        UserRole(user_id=str(uuid4()), role=UserRoleType.BUYER),
    )


def test_deleting_user_cascades_to_roles(db_session: Session) -> None:
    user = create_user(db_session, "role-cascade")
    role = UserRole(user_id=user.id, role=UserRoleType.BUYER)
    db_session.add(role)
    db_session.flush()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.flush()

    remaining = db_session.scalar(
        select(func.count()).select_from(UserRole).where(UserRole.id == role.id)
    )
    assert remaining == 0


def test_refresh_token_uses_hash_and_valid_user(db_session: Session) -> None:
    user = create_user(db_session, "refresh-token")
    token = RefreshToken(
        user_id=user.id,
        token_hash="refresh-token-hash",
        expires_at=utc_now() + timedelta(days=7),
    )
    db_session.add(token)
    db_session.flush()

    columns = set(RefreshToken.__table__.columns.keys())
    assert token.id is not None
    assert "token_hash" in columns
    assert "token" not in columns
    assert "raw_token" not in columns


def test_refresh_token_hash_is_unique(db_session: Session) -> None:
    user = create_user(db_session, "unique-refresh-token")
    expiry = utc_now() + timedelta(days=7)
    db_session.add_all(
        [
            RefreshToken(user_id=user.id, token_hash="same-token-hash", expires_at=expiry),
            RefreshToken(user_id=user.id, token_hash="same-token-hash", expires_at=expiry),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_refresh_token_requires_existing_user(db_session: Session) -> None:
    assert_foreign_key_rejected(
        db_session,
        RefreshToken(
            user_id=str(uuid4()),
            token_hash="orphan-refresh-token-hash",
            expires_at=utc_now() + timedelta(days=7),
        ),
    )


def test_deleting_user_cascades_to_refresh_tokens(db_session: Session) -> None:
    user = create_user(db_session, "refresh-cascade")
    token = RefreshToken(
        user_id=user.id,
        token_hash="cascade-refresh-token-hash",
        expires_at=utc_now() + timedelta(days=7),
    )
    db_session.add(token)
    db_session.flush()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.flush()

    remaining = db_session.scalar(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.id == token.id)
    )
    assert remaining == 0


def test_phone_verification_code_uses_hash_and_defaults(db_session: Session) -> None:
    user = create_user(db_session, "phone-code")
    verification = PhoneVerificationCode(
        user_id=user.id,
        phone_number="+8613800000020",
        code_hash="phone-code-hash",
        expires_at=utc_now() + timedelta(minutes=5),
    )
    db_session.add(verification)
    db_session.flush()

    columns = set(PhoneVerificationCode.__table__.columns.keys())
    assert verification.attempts == 0
    assert "code_hash" in columns
    assert "otp" not in columns
    assert "otp_code" not in columns
    assert "raw_code" not in columns


def test_phone_verification_attempts_cannot_be_negative(db_session: Session) -> None:
    user = create_user(db_session, "negative-attempts")
    db_session.add(
        PhoneVerificationCode(
            user_id=user.id,
            phone_number="+8613800000021",
            code_hash="negative-attempt-code-hash",
            expires_at=utc_now() + timedelta(minutes=5),
            attempts=-1,
        )
    )

    with pytest.raises(DBAPIError):
        db_session.flush()


def test_phone_verification_code_requires_existing_user(db_session: Session) -> None:
    assert_foreign_key_rejected(
        db_session,
        PhoneVerificationCode(
            user_id=str(uuid4()),
            phone_number="+8613800000022",
            code_hash="orphan-phone-code-hash",
            expires_at=utc_now() + timedelta(minutes=5),
        ),
    )


def test_deleting_user_cascades_to_phone_codes(db_session: Session) -> None:
    user = create_user(db_session, "phone-cascade")
    verification = PhoneVerificationCode(
        user_id=user.id,
        phone_number="+8613800000023",
        code_hash="cascade-phone-code-hash",
        expires_at=utc_now() + timedelta(minutes=5),
    )
    db_session.add(verification)
    db_session.flush()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.flush()

    remaining = db_session.scalar(
        select(func.count())
        .select_from(PhoneVerificationCode)
        .where(PhoneVerificationCode.id == verification.id)
    )
    assert remaining == 0


def test_password_reset_code_uses_hash_and_valid_user(db_session: Session) -> None:
    user = create_user(db_session, "reset-code")
    reset = PasswordResetCode(
        user_id=user.id,
        code_hash="password-reset-code-hash",
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(reset)
    db_session.flush()

    columns = set(PasswordResetCode.__table__.columns.keys())
    assert reset.id is not None
    assert "code_hash" in columns
    assert "reset_code" not in columns
    assert "raw_code" not in columns


def test_password_reset_code_requires_existing_user(db_session: Session) -> None:
    assert_foreign_key_rejected(
        db_session,
        PasswordResetCode(
            user_id=str(uuid4()),
            code_hash="orphan-reset-code-hash",
            expires_at=utc_now() + timedelta(minutes=10),
        ),
    )


def test_deleting_user_cascades_to_password_reset_codes(db_session: Session) -> None:
    user = create_user(db_session, "reset-cascade")
    reset = PasswordResetCode(
        user_id=user.id,
        code_hash="cascade-reset-code-hash",
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(reset)
    db_session.flush()

    db_session.execute(delete(User).where(User.id == user.id))
    db_session.flush()

    remaining = db_session.scalar(
        select(func.count()).select_from(PasswordResetCode).where(PasswordResetCode.id == reset.id)
    )
    assert remaining == 0
