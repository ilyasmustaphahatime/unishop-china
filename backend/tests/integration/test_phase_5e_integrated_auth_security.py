from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus, UserRoleType
from app.core.config import Settings
from app.core.database import engine
from app.core.exceptions import (
    EmailVerificationError,
    InvalidPasswordChangeError,
    InvalidPasswordResetError,
    PhoneVerificationError,
    SessionRefreshError,
    TokenValidationError,
)
from app.core.security import (
    hash_email_verification_code,
    hash_password,
    hash_password_reset_code,
    hash_verification_code,
    verify_password,
)
from app.integrations.email_verification_delivery import (
    DisabledEmailVerificationDeliveryProvider,
)
from app.integrations.sms_client import FakeSmsSender
from app.main import create_app
from app.models import (
    EmailVerificationCode,
    PasswordResetCode,
    PhoneVerificationCode,
    RefreshToken,
    User,
    UserRole,
)
from app.models.base import utc_now
from app.services.email_verification_service import EmailVerificationService
from app.services.password_change_service import PasswordChangeService
from app.services.password_reset_service import PasswordResetCompletionService
from app.services.phone_verification_service import PhoneVerificationService
from app.services.refresh_session_service import RefreshSessionService
from app.services.token_service import AccessTokenService

JWT_SECRET = "phase-5e-jwt-secret-with-more-than-thirty-two-characters"
CODE_SECRET = "phase-5e-code-secret-with-more-than-thirty-two-characters"
OLD_PASSWORD = "PhaseFiveEOldPassword123"
RESET_PASSWORD = "PhaseFiveEResetPassword456"
CHANGE_PASSWORD = "PhaseFiveEChangePassword789"
PHONE_CODE = "135790"
EMAIL_CODE = "246801"
RESET_CODE = "975310"


def phase_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "app_debug": False,
        "jwt_secret_key": JWT_SECRET,
        "verification_code_hash_secret": CODE_SECRET,
        "jwt_algorithm": "HS256",
        "jwt_issuer": "unishop-china-api",
        "jwt_audience": "unishop-china-web",
        "jwt_clock_skew_seconds": 0,
        "email_verification_delivery_provider": "disabled",
        "password_reset_delivery_provider": "disabled",
    }
    values.update(overrides)
    return Settings(**values)


def database_snapshot() -> tuple[tuple[int, ...], frozenset[str]]:
    models = (
        User,
        UserRole,
        PhoneVerificationCode,
        RefreshToken,
        PasswordResetCode,
        EmailVerificationCode,
    )
    with Session(engine) as session:
        counts = tuple(
            int(session.scalar(select(func.count()).select_from(model)) or 0)
            for model in models
        )
        return counts, frozenset(session.scalars(select(User.id)))


def create_user(session: Session, *, label: str) -> User:
    user = User(
        email=f"phase5e-{label}-{uuid4().hex}@example.invalid",
        phone_number=f"+86139{uuid4().int % 100_000_000:08d}",
        password_hash=hash_password(OLD_PASSWORD),
        account_status=AccountStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
    session.flush()
    return user


def cleanup_user(user_id: str | None) -> None:
    if user_id is None:
        return
    with Session(engine) as session, session.begin():
        session.execute(delete(User).where(User.id == user_id))


def create_committed_security_fixture(
    label: str,
) -> tuple[str, str, str, str]:
    config = phase_settings()
    now = utc_now()
    with Session(engine) as session, session.begin():
        user = create_user(session, label=label)
        session.add(
            PasswordResetCode(
                user_id=user.id,
                code_hash=hash_password_reset_code(RESET_CODE, CODE_SECRET),
                expires_at=now + timedelta(minutes=10),
                attempts=0,
                created_at=now,
            )
        )
        cookies = RefreshSessionService(config).create_login_session(
            session,
            user_id=user.id,
        )
        return user.id, user.email, cookies.refresh_token, cookies.csrf_token


def test_cross_purpose_challenge_matrix_allows_only_matching_purpose(
    db_session: Session,
) -> None:
    now = utc_now()
    user = create_user(db_session, label="purpose-matrix")
    db_session.add_all(
        [
            PhoneVerificationCode(
                user_id=user.id,
                phone_number=user.phone_number,
                code_hash=hash_verification_code(PHONE_CODE, CODE_SECRET),
                expires_at=now + timedelta(minutes=10),
                created_at=now,
            ),
            EmailVerificationCode(
                user_id=user.id,
                code_hash=hash_email_verification_code(EMAIL_CODE, CODE_SECRET),
                expires_at=now + timedelta(minutes=10),
                attempts=0,
                activated_at=now,
                created_at=now,
            ),
            PasswordResetCode(
                user_id=user.id,
                code_hash=hash_password_reset_code(RESET_CODE, CODE_SECRET),
                expires_at=now + timedelta(minutes=10),
                attempts=0,
                created_at=now,
            ),
        ]
    )
    user_id = user.id
    email_address = user.email
    phone_number = user.phone_number
    assert email_address is not None and phone_number is not None
    db_session.commit()

    phone = PhoneVerificationService(
        sms_sender=FakeSmsSender(),
        verification_code_hash_secret=CODE_SECRET,
    )
    email = EmailVerificationService(
        phase_settings(),
        delivery_provider=DisabledEmailVerificationDeliveryProvider(),
    )
    reset = PasswordResetCompletionService(phase_settings())

    for wrong_purpose_code in (EMAIL_CODE, RESET_CODE):
        with pytest.raises(PhoneVerificationError):
            phone.verify(db_session, phone_number, wrong_purpose_code)
    for wrong_purpose_code in (PHONE_CODE, RESET_CODE):
        with pytest.raises(EmailVerificationError):
            email.verify(
                db_session,
                user_id=user_id,
                submitted_code=wrong_purpose_code,
            )
    for wrong_purpose_code in (PHONE_CODE, EMAIL_CODE):
        with pytest.raises(InvalidPasswordResetError):
            reset.reset_password(
                db_session,
                identifier=email_address,
                identifier_kind="email",
                code=wrong_purpose_code,
                new_password=RESET_PASSWORD,
            )

    assert phone.verify(db_session, phone_number, PHONE_CODE).phone_verified
    assert email.verify(
        db_session,
        user_id=user_id,
        submitted_code=EMAIL_CODE,
    ).email_verified
    reset.reset_password(
        db_session,
        identifier=email_address,
        identifier_kind="email",
        code=RESET_CODE,
        new_password=RESET_PASSWORD,
    )
    persisted_user = db_session.get(User, user_id)
    assert persisted_user is not None
    assert persisted_user.phone_verified is True
    assert persisted_user.email_verified is True
    assert verify_password(RESET_PASSWORD, persisted_user.password_hash)


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"nbf": datetime.now(timezone.utc) + timedelta(minutes=1)},
        {"iat": datetime.now(timezone.utc) + timedelta(minutes=1)},
        {"sub": str(uuid4()).upper()},
        {"jti": 12345},
        {"type": "refresh"},
    ],
)
def test_extended_jwt_adversarial_claims_are_rejected(
    claim_overrides: dict[str, object],
) -> None:
    config = phase_settings()
    now = datetime.now(timezone.utc)
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "type": "access",
        "jti": "phase-5e-synthetic-jti",
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
    }
    claims.update(claim_overrides)
    token = jwt.encode(claims, JWT_SECRET, algorithm="HS256")
    with pytest.raises(TokenValidationError):
        AccessTokenService(config).decode_access_token(token)


def test_production_openapi_never_mounts_development_providers() -> None:
    config = phase_settings(
        app_env="production",
        frontend_url="https://shop.example.test",
        refresh_cookie_secure=True,
        sms_enabled=False,
        sms_provider="tencent",
        enable_fake_sms_dev_inbox=False,
        password_reset_delivery_provider="disabled",
        enable_fake_password_reset_dev_inbox=False,
        email_verification_delivery_provider="disabled",
        enable_fake_email_verification_dev_inbox=False,
    )
    paths = create_app(config).openapi()["paths"]
    assert not any("/dev/" in path for path in paths)
    auth_operations = [
        (method, path)
        for path, operations in paths.items()
        for method in operations
        if path.startswith("/api/v1/auth/")
        and method in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(auth_operations) == 13
    assert len(auth_operations) == len(set(auth_operations))


def test_password_reset_vs_refresh_preserves_successful_reset_authority() -> None:
    baseline = database_snapshot()
    user_id: str | None = None
    try:
        user_id, email, raw_refresh, csrf = create_committed_security_fixture(
            "reset-refresh"
        )
        barrier = Barrier(2)

        def reset_password() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    PasswordResetCompletionService(phase_settings()).reset_password(
                        session,
                        identifier=email,
                        identifier_kind="email",
                        code=RESET_CODE,
                        new_password=RESET_PASSWORD,
                    )
                except InvalidPasswordResetError:
                    return "rejected"
                except OperationalError:
                    return "database-retry-required"
                return "reset"

        def refresh() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    RefreshSessionService(phase_settings()).rotate_session(
                        session,
                        raw_refresh_token=raw_refresh,
                        csrf_cookie=csrf,
                        csrf_header=csrf,
                    )
                except SessionRefreshError:
                    return "rejected"
                except OperationalError:
                    return "database-retry-required"
                return "rotated"

        with ThreadPoolExecutor(max_workers=2) as executor:
            reset_future = executor.submit(reset_password)
            refresh_future = executor.submit(refresh)
            reset_outcome = reset_future.result(timeout=20)
            refresh_outcome = refresh_future.result(timeout=20)

        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(PasswordResetCode).where(
                    PasswordResetCode.user_id == user_id
                )
            )
            refresh_rows = list(
                audit.scalars(
                    select(RefreshToken).where(RefreshToken.user_id == user_id)
                )
            )
            assert user is not None and challenge is not None and refresh_rows
            if reset_outcome == "reset":
                assert verify_password(RESET_PASSWORD, user.password_hash)
                assert challenge.used_at is not None
                assert all(row.revoked_at is not None for row in refresh_rows)
            else:
                assert reset_outcome == "database-retry-required"
                assert refresh_outcome == "rotated"
                assert verify_password(OLD_PASSWORD, user.password_hash)
                assert challenge.used_at is None
    finally:
        cleanup_user(user_id)
    assert database_snapshot() == baseline


def test_password_change_vs_refresh_preserves_successful_change_authority() -> None:
    baseline = database_snapshot()
    user_id: str | None = None
    try:
        user_id, _, raw_refresh, csrf = create_committed_security_fixture(
            "change-refresh"
        )
        barrier = Barrier(2)

        def change_password() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    PasswordChangeService().change_password(
                        session,
                        user_id=user_id,
                        current_password=OLD_PASSWORD,
                        new_password=CHANGE_PASSWORD,
                    )
                except InvalidPasswordChangeError:
                    return "rejected"
                except OperationalError:
                    return "database-retry-required"
                return "changed"

        def refresh() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    RefreshSessionService(phase_settings()).rotate_session(
                        session,
                        raw_refresh_token=raw_refresh,
                        csrf_cookie=csrf,
                        csrf_header=csrf,
                    )
                except SessionRefreshError:
                    return "rejected"
                except OperationalError:
                    return "database-retry-required"
                return "rotated"

        with ThreadPoolExecutor(max_workers=2) as executor:
            change_future = executor.submit(change_password)
            refresh_future = executor.submit(refresh)
            change_outcome = change_future.result(timeout=20)
            refresh_outcome = refresh_future.result(timeout=20)

        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(PasswordResetCode).where(
                    PasswordResetCode.user_id == user_id
                )
            )
            refresh_rows = list(
                audit.scalars(
                    select(RefreshToken).where(RefreshToken.user_id == user_id)
                )
            )
            assert user is not None and challenge is not None and refresh_rows
            if change_outcome == "changed":
                assert verify_password(CHANGE_PASSWORD, user.password_hash)
                assert challenge.used_at is not None
                assert all(row.revoked_at is not None for row in refresh_rows)
            else:
                assert change_outcome == "database-retry-required"
                assert refresh_outcome == "rotated"
                assert verify_password(OLD_PASSWORD, user.password_hash)
                assert challenge.used_at is None
    finally:
        cleanup_user(user_id)
    assert database_snapshot() == baseline


def test_password_reset_vs_change_allows_one_credential_authority() -> None:
    baseline = database_snapshot()
    user_id: str | None = None
    try:
        user_id, email, _, _ = create_committed_security_fixture("reset-change")
        barrier = Barrier(2)

        def reset_password() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    PasswordResetCompletionService(phase_settings()).reset_password(
                        session,
                        identifier=email,
                        identifier_kind="email",
                        code=RESET_CODE,
                        new_password=RESET_PASSWORD,
                    )
                except InvalidPasswordResetError:
                    return "rejected"
                return "reset"

        def change_password() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    PasswordChangeService().change_password(
                        session,
                        user_id=user_id,
                        current_password=OLD_PASSWORD,
                        new_password=CHANGE_PASSWORD,
                    )
                except InvalidPasswordChangeError:
                    return "rejected"
                return "changed"

        with ThreadPoolExecutor(max_workers=2) as executor:
            reset_future = executor.submit(reset_password)
            change_future = executor.submit(change_password)
            outcomes = [
                reset_future.result(timeout=20),
                change_future.result(timeout=20),
            ]

        assert sorted(outcomes) in (["changed", "rejected"], ["rejected", "reset"])
        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(PasswordResetCode).where(
                    PasswordResetCode.user_id == user_id
                )
            )
            refresh_rows = list(
                audit.scalars(
                    select(RefreshToken).where(RefreshToken.user_id == user_id)
                )
            )
            assert user is not None and challenge is not None and refresh_rows
            winner = RESET_PASSWORD if "reset" in outcomes else CHANGE_PASSWORD
            assert verify_password(winner, user.password_hash)
            assert not verify_password(OLD_PASSWORD, user.password_hash)
            assert challenge.used_at is not None
            assert all(row.revoked_at is not None for row in refresh_rows)
    finally:
        cleanup_user(user_id)
    assert database_snapshot() == baseline


def test_logout_all_vs_refresh_leaves_no_active_descendant() -> None:
    baseline = database_snapshot()
    user_id: str | None = None
    try:
        user_id, _, raw_refresh, csrf = create_committed_security_fixture(
            "logout-all-refresh"
        )
        barrier = Barrier(2)

        def logout_all() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    RefreshSessionService(phase_settings()).logout_all(
                        session,
                        user_id=user_id,
                    )
                except OperationalError:
                    return "database-retry-required"
                return "logged-out"

        def refresh() -> str:
            barrier.wait(timeout=10)
            with Session(engine) as session:
                try:
                    RefreshSessionService(phase_settings()).rotate_session(
                        session,
                        raw_refresh_token=raw_refresh,
                        csrf_cookie=csrf,
                        csrf_header=csrf,
                    )
                except SessionRefreshError:
                    return "rejected"
                except OperationalError:
                    return "database-retry-required"
                return "rotated"

        with ThreadPoolExecutor(max_workers=2) as executor:
            logout_future = executor.submit(logout_all)
            refresh_future = executor.submit(refresh)
            logout_outcome = logout_future.result(timeout=20)
            refresh_outcome = refresh_future.result(timeout=20)

        if logout_outcome == "database-retry-required":
            assert refresh_outcome == "rotated"
            with Session(engine) as retry_session:
                RefreshSessionService(phase_settings()).logout_all(
                    retry_session,
                    user_id=user_id,
                )
        else:
            assert logout_outcome == "logged-out"
            assert refresh_outcome in {"rotated", "rejected"}
        with Session(engine) as audit:
            rows = list(
                audit.scalars(
                    select(RefreshToken).where(RefreshToken.user_id == user_id)
                )
            )
            assert rows and all(row.revoked_at is not None for row in rows)
    finally:
        cleanup_user(user_id)
    assert database_snapshot() == baseline
