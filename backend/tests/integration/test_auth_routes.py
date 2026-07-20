from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import get_registration_service
from app.common.enums import UserRoleType
from app.core.database import get_db
from app.core.security import verify_password, verify_verification_code
from app.main import app
from app.integrations.sms_client import FakeSmsSender
from app.models import PhoneVerificationCode, User, UserRole
from app.repositories.phone_verification_code_repository import (
    PhoneVerificationCodeRepository,
)
from app.repositories.role_repository import UserRoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegisterRequest
from app.services.auth_service import RegistrationService

TEST_CODE = "123456"
TEST_CODE_SECRET = "integration-test-verification-code-secret-with-enough-entropy"
STRONG_PASSWORD = "StrongPassword123"
FORBIDDEN_RESPONSE_FIELDS = {
    "password",
    "password_hash",
    "code",
    "otp",
    "code_hash",
    "token",
    "jwt",
    "refresh_token",
    "access_token",
}


def build_registration_service(
    *,
    user_repository: UserRepository | None = None,
    role_repository: UserRoleRepository | None = None,
    phone_code_repository: PhoneVerificationCodeRepository | None = None,
    secret: str | None = TEST_CODE_SECRET,
    sms_sender: FakeSmsSender | None = None,
) -> RegistrationService:
    return RegistrationService(
        user_repository=user_repository,
        role_repository=role_repository,
        phone_code_repository=phone_code_repository,
        verification_code_hash_secret=secret,
        verification_code_generator=lambda: TEST_CODE,
        sms_sender=sms_sender or FakeSmsSender(),
    )


@pytest.fixture
def registration_service() -> RegistrationService:
    return build_registration_service()


@pytest.fixture
def client(
    db_session: Session,
    registration_service: RegistrationService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_registration_service] = lambda: registration_service
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def get_user_by_email(db_session: Session, email: str) -> User | None:
    return db_session.scalar(select(User).where(User.email == email))


def count_for_user(
    db_session: Session, model: type[UserRole] | type[PhoneVerificationCode], user_id: str
) -> int:
    return (
        db_session.scalar(select(func.count()).select_from(model).where(model.user_id == user_id))
        or 0
    )


def assert_safe_registration_response(payload: dict[str, object]) -> None:
    assert FORBIDDEN_RESPONSE_FIELDS.isdisjoint(payload)


def test_email_only_registration_creates_safe_buyer_account(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "  EMAIL.USER@EXAMPLE.COM ", "password": STRONG_PASSWORD},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "email.user@example.com"
    assert payload["phone_number"] is None
    assert payload["roles"] == ["BUYER"]
    assert payload["phone_verification_required"] is False
    assert payload["phone_verified"] is False
    assert payload["email_verified"] is False
    assert payload["account_status"] == "ACTIVE"
    assert_safe_registration_response(payload)

    user = get_user_by_email(db_session, "email.user@example.com")
    assert user is not None
    assert db_session.scalar(select(func.count()).select_from(User)) == 1
    assert user.password_hash != STRONG_PASSWORD
    assert verify_password(STRONG_PASSWORD, user.password_hash) is True
    assert verify_password("WrongPassword123", user.password_hash) is False
    assert user.phone_verified is False
    assert user.email_verified is False
    assert user.account_status.value == "ACTIVE"
    roles = db_session.scalars(select(UserRole.role).where(UserRole.user_id == user.id)).all()
    assert roles == [UserRoleType.BUYER]
    assert count_for_user(db_session, PhoneVerificationCode, user.id) == 0


def test_phone_only_registration_creates_hashed_verification_code(
    client: TestClient,
    db_session: Session,
) -> None:
    before_request = datetime.now(timezone.utc)
    response = client.post(
        "/api/v1/auth/register",
        json={"phone_number": "+86 138 0000 0000", "password": STRONG_PASSWORD},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] is None
    assert payload["phone_number"] == "+8613800000000"
    assert payload["phone_verification_required"] is True
    assert payload["roles"] == ["BUYER"]
    assert_safe_registration_response(payload)

    user = db_session.scalar(select(User).where(User.phone_number == "+8613800000000"))
    assert user is not None
    verification = db_session.scalar(
        select(PhoneVerificationCode).where(PhoneVerificationCode.user_id == user.id)
    )
    assert verification is not None
    assert verification.phone_number == "+8613800000000"
    assert verification.code_hash != TEST_CODE
    assert verify_verification_code(TEST_CODE, verification.code_hash, TEST_CODE_SECRET) is True
    assert verification.attempts == 0
    assert verification.verified_at is None
    expires_at = verification.expires_at.replace(tzinfo=timezone.utc)
    seconds_until_expiry = (expires_at - before_request).total_seconds()
    assert 590 <= seconds_until_expiry <= 610


def test_email_and_phone_registration_creates_one_buyer_and_one_code(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "both@example.com",
            "phone_number": "13900000000",
            "password": STRONG_PASSWORD,
        },
    )

    assert response.status_code == 201
    assert_safe_registration_response(response.json())
    user = get_user_by_email(db_session, "both@example.com")
    assert user is not None
    roles = db_session.scalars(select(UserRole.role).where(UserRole.user_id == user.id)).all()
    assert roles == [UserRoleType.BUYER]
    assert UserRoleType.SELLER not in roles
    assert UserRoleType.ADMIN not in roles
    assert count_for_user(db_session, PhoneVerificationCode, user.id) == 1


def test_normalized_duplicate_email_returns_safe_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/v1/auth/register",
        json={"email": "Case.User@Example.com", "password": STRONG_PASSWORD},
    )
    second = client.post(
        "/api/v1/auth/register",
        json={"email": "  case.user@example.com ", "password": STRONG_PASSWORD},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {
        "detail": {
            "code": "EMAIL_ALREADY_REGISTERED",
            "message": "An account with this email already exists.",
        }
    }


def test_normalized_duplicate_phone_returns_safe_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/v1/auth/register",
        json={"phone_number": "13700000000", "password": STRONG_PASSWORD},
    )
    second = client.post(
        "/api/v1/auth/register",
        json={"phone_number": "0086 13700000000", "password": STRONG_PASSWORD},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "PHONE_ALREADY_REGISTERED"


@pytest.mark.parametrize(
    "request_body",
    [
        {"password": STRONG_PASSWORD},
        {"email": "not-an-email", "password": STRONG_PASSWORD},
        {"phone_number": "12345", "password": STRONG_PASSWORD},
        {"email": "weak@example.com", "password": "weak"},
        {"email": "role@example.com", "password": STRONG_PASSWORD, "role": "ADMIN"},
        {
            "email": "status@example.com",
            "password": STRONG_PASSWORD,
            "account_status": "ACTIVE",
        },
        {"email": "roles@example.com", "password": STRONG_PASSWORD, "roles": ["ADMIN"]},
        {"email": "admin@example.com", "password": STRONG_PASSWORD, "is_admin": True},
        {
            "email": "phone-verified@example.com",
            "password": STRONG_PASSWORD,
            "phone_verified": True,
        },
        {
            "email": "email-verified@example.com",
            "password": STRONG_PASSWORD,
            "email_verified": True,
        },
        {
            "email": "hash@example.com",
            "password": STRONG_PASSWORD,
            "password_hash": "client-controlled",
        },
        {
            "email": "created@example.com",
            "password": STRONG_PASSWORD,
            "created_at": "2026-07-17T00:00:00Z",
        },
        {
            "email": "updated@example.com",
            "password": STRONG_PASSWORD,
            "updated_at": "2026-07-17T00:00:00Z",
        },
    ],
    ids=[
        "missing-identifier",
        "invalid-email",
        "invalid-phone",
        "weak-password",
        "forbidden-role",
        "forbidden-account-status",
        "forbidden-roles",
        "forbidden-is-admin",
        "forbidden-phone-verified",
        "forbidden-email-verified",
        "forbidden-password-hash",
        "forbidden-created-at",
        "forbidden-updated-at",
    ],
)
def test_invalid_registration_requests_return_422(
    client: TestClient,
    request_body: dict[str, object],
) -> None:
    response = client.post("/api/v1/auth/register", json=request_body)
    assert response.status_code == 422


class FailingRoleRepository(UserRoleRepository):
    def create_role(
        self,
        session: Session,
        *,
        user_id: str,
        role: UserRoleType,
    ) -> UserRole:
        raise RuntimeError("simulated role persistence failure")


class FailingPhoneCodeRepository(PhoneVerificationCodeRepository):
    def create_code(self, session: Session, **kwargs: object) -> PhoneVerificationCode:
        raise RuntimeError("simulated phone-code persistence failure")


class IntegrityRaceUserRepository(UserRepository):
    def create(
        self,
        session: Session,
        *,
        email: str | None,
        phone_number: str | None,
        password_hash: str,
    ) -> User:
        raise IntegrityError("INSERT INTO users", {}, Exception("simulated duplicate race"))


class ConstraintIntegrityRaceUserRepository(UserRepository):
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name

    def create(
        self,
        session: Session,
        *,
        email: str | None,
        phone_number: str | None,
        password_hash: str,
    ) -> User:
        message = f"Duplicate entry for key 'users.{self.constraint_name}'"
        raise IntegrityError("INSERT INTO users", {}, Exception(message))


def test_role_failure_rolls_back_user_and_code(db_session: Session) -> None:
    service = build_registration_service(role_repository=FailingRoleRepository())
    request = RegisterRequest(
        email="role.failure@example.com",
        phone_number="13600000000",
        password=STRONG_PASSWORD,
    )

    with pytest.raises(RuntimeError):
        service.register(db_session, request)

    assert get_user_by_email(db_session, "role.failure@example.com") is None
    assert db_session.scalar(select(func.count()).select_from(PhoneVerificationCode)) == 0


def test_phone_code_failure_rolls_back_user_and_buyer_role(db_session: Session) -> None:
    service = build_registration_service(
        phone_code_repository=FailingPhoneCodeRepository(),
    )
    request = RegisterRequest(
        email="code.failure@example.com",
        phone_number="13500000000",
        password=STRONG_PASSWORD,
    )

    with pytest.raises(RuntimeError):
        service.register(db_session, request)

    assert get_user_by_email(db_session, "code.failure@example.com") is None
    assert db_session.scalar(select(func.count()).select_from(UserRole)) == 0


def test_integrity_error_race_becomes_safe_409(
    client: TestClient,
) -> None:
    app.dependency_overrides[get_registration_service] = lambda: build_registration_service(
        user_repository=IntegrityRaceUserRepository()
    )

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "race@example.com", "password": STRONG_PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REGISTRATION_CONFLICT"
    assert "INSERT" not in response.text
    assert "unishop_china" not in response.text


@pytest.mark.parametrize(
    ("constraint_name", "request_body", "expected_code"),
    [
        (
            "ix_users_email",
            {"email": "email.race@example.com", "password": STRONG_PASSWORD},
            "EMAIL_ALREADY_REGISTERED",
        ),
        (
            "ix_users_phone_number",
            {"phone_number": "13300000000", "password": STRONG_PASSWORD},
            "PHONE_ALREADY_REGISTERED",
        ),
    ],
    ids=["email", "phone"],
)
def test_known_integrity_constraint_returns_identifier_specific_safe_409(
    client: TestClient,
    constraint_name: str,
    request_body: dict[str, str],
    expected_code: str,
) -> None:
    repository = ConstraintIntegrityRaceUserRepository(constraint_name)
    app.dependency_overrides[get_registration_service] = lambda: build_registration_service(
        user_repository=repository
    )

    response = client.post("/api/v1/auth/register", json=request_body)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == expected_code
    assert constraint_name not in response.text
    assert "INSERT" not in response.text


def test_unexpected_role_failure_returns_safe_500_and_rolls_back(
    client: TestClient,
    db_session: Session,
) -> None:
    app.dependency_overrides[get_registration_service] = lambda: build_registration_service(
        role_repository=FailingRoleRepository()
    )

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "safe.failure@example.com", "password": STRONG_PASSWORD},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "REGISTRATION_FAILED",
            "message": "Registration could not be completed.",
        }
    }
    assert "simulated" not in response.text
    assert get_user_by_email(db_session, "safe.failure@example.com") is None


def test_missing_phone_code_secret_returns_safe_500(
    client: TestClient,
    db_session: Session,
) -> None:
    app.dependency_overrides[get_registration_service] = lambda: build_registration_service(
        secret=None
    )

    response = client.post(
        "/api/v1/auth/register",
        json={"phone_number": "13400000000", "password": STRONG_PASSWORD},
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "REGISTRATION_UNAVAILABLE"
    assert "VERIFICATION_CODE_HASH_SECRET" not in response.text
    assert db_session.scalar(select(func.count()).select_from(User)) == 0
