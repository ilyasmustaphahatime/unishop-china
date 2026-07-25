from collections.abc import Generator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_registration_rate_limiter,
    get_registration_service,
)
from app.common.enums import UserRoleType
from app.core.database import get_db
from app.core.rate_limit import InMemoryRateLimiter
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
    app.dependency_overrides[get_registration_rate_limiter] = lambda: InMemoryRateLimiter(
        max_requests=1000,
        window_seconds=60,
        max_keys=100,
    )
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


def unique_email(label: str) -> str:
    return f"{label}.{uuid4().hex}@example.com"


def unique_phone() -> str:
    return f"138{uuid4().int % 100_000_000:08d}"


def test_email_only_registration_creates_safe_buyer_account(
    client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("email-user")
    baseline_users = int(db_session.scalar(select(func.count()).select_from(User)) or 0)
    db_session.commit()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"  {email.upper()} ", "password": STRONG_PASSWORD},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == email
    assert payload["phone_number"] is None
    assert payload["roles"] == ["BUYER"]
    assert payload["phone_verification_required"] is False
    assert payload["phone_verified"] is False
    assert payload["email_verified"] is False
    assert payload["account_status"] == "ACTIVE"
    assert_safe_registration_response(payload)

    user = get_user_by_email(db_session, email)
    assert user is not None
    assert db_session.scalar(select(func.count()).select_from(User)) == baseline_users + 1
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
    phone = unique_phone()
    before_request = datetime.now(timezone.utc)
    response = client.post(
        "/api/v1/auth/register",
        json={"phone_number": phone, "password": STRONG_PASSWORD},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] is None
    normalized_phone = f"+86{phone}"
    assert payload["phone_number"] == normalized_phone
    assert payload["phone_verification_required"] is True
    assert payload["roles"] == ["BUYER"]
    assert_safe_registration_response(payload)

    user = db_session.scalar(select(User).where(User.phone_number == normalized_phone))
    assert user is not None
    verification = db_session.scalar(
        select(PhoneVerificationCode).where(PhoneVerificationCode.user_id == user.id)
    )
    assert verification is not None
    assert verification.phone_number == normalized_phone
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
    email = unique_email("both")
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "phone_number": unique_phone(),
            "password": STRONG_PASSWORD,
        },
    )

    assert response.status_code == 201
    assert_safe_registration_response(response.json())
    user = get_user_by_email(db_session, email)
    assert user is not None
    roles = db_session.scalars(select(UserRole.role).where(UserRole.user_id == user.id)).all()
    assert roles == [UserRoleType.BUYER]
    assert UserRoleType.SELLER not in roles
    assert UserRoleType.ADMIN not in roles
    assert count_for_user(db_session, PhoneVerificationCode, user.id) == 1


def test_normalized_duplicate_email_returns_safe_conflict(client: TestClient) -> None:
    email = unique_email("case-user")
    first = client.post(
        "/api/v1/auth/register",
        json={"email": email.upper(), "password": STRONG_PASSWORD},
    )
    second = client.post(
        "/api/v1/auth/register",
        json={"email": f"  {email} ", "password": STRONG_PASSWORD},
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
    phone = unique_phone()
    first = client.post(
        "/api/v1/auth/register",
        json={"phone_number": phone, "password": STRONG_PASSWORD},
    )
    second = client.post(
        "/api/v1/auth/register",
        json={"phone_number": f"0086 {phone}", "password": STRONG_PASSWORD},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "PHONE_ALREADY_REGISTERED"


def test_registration_rate_limit_uses_connection_peer_and_returns_safe_error(
    client: TestClient,
    db_session: Session,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_registration_rate_limiter] = lambda: limiter
    first_email = unique_email("rate-limit-first")
    blocked_email = unique_email("rate-limit-blocked")

    first = client.post(
        "/api/v1/auth/register",
        json={"email": first_email, "password": STRONG_PASSWORD},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    blocked = client.post(
        "/api/v1/auth/register",
        json={"email": blocked_email, "password": STRONG_PASSWORD},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )

    assert first.status_code == 201
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.json() == {
        "detail": {
            "code": "REGISTRATION_RATE_LIMITED",
            "message": "Too many registration attempts. Please try again later.",
        }
    }
    assert blocked_email not in blocked.text
    assert STRONG_PASSWORD not in blocked.text
    assert get_user_by_email(db_session, blocked_email) is None


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
    email = unique_email("role-failure")
    baseline_codes = int(
        db_session.scalar(select(func.count()).select_from(PhoneVerificationCode)) or 0
    )
    db_session.commit()
    service = build_registration_service(role_repository=FailingRoleRepository())
    request = RegisterRequest(
        email=email,
        phone_number=unique_phone(),
        password=STRONG_PASSWORD,
    )

    with pytest.raises(RuntimeError):
        service.register(db_session, request)

    assert get_user_by_email(db_session, email) is None
    assert (
        db_session.scalar(select(func.count()).select_from(PhoneVerificationCode)) == baseline_codes
    )


def test_phone_code_failure_rolls_back_user_and_buyer_role(db_session: Session) -> None:
    email = unique_email("code-failure")
    baseline_roles = int(db_session.scalar(select(func.count()).select_from(UserRole)) or 0)
    db_session.commit()
    service = build_registration_service(
        phone_code_repository=FailingPhoneCodeRepository(),
    )
    request = RegisterRequest(
        email=email,
        phone_number=unique_phone(),
        password=STRONG_PASSWORD,
    )

    with pytest.raises(RuntimeError):
        service.register(db_session, request)

    assert get_user_by_email(db_session, email) is None
    assert db_session.scalar(select(func.count()).select_from(UserRole)) == baseline_roles


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
    email = unique_email("safe-failure")
    app.dependency_overrides[get_registration_service] = lambda: build_registration_service(
        role_repository=FailingRoleRepository()
    )

    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": STRONG_PASSWORD},
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "REGISTRATION_FAILED",
            "message": "Registration could not be completed.",
        }
    }
    assert "simulated" not in response.text
    assert get_user_by_email(db_session, email) is None


def test_missing_phone_code_secret_returns_safe_500(
    client: TestClient,
    db_session: Session,
) -> None:
    phone = unique_phone()
    baseline_users = int(db_session.scalar(select(func.count()).select_from(User)) or 0)
    db_session.commit()
    app.dependency_overrides[get_registration_service] = lambda: build_registration_service(
        secret=None
    )

    response = client.post(
        "/api/v1/auth/register",
        json={"phone_number": phone, "password": STRONG_PASSWORD},
    )

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "REGISTRATION_UNAVAILABLE"
    assert "VERIFICATION_CODE_HASH_SECRET" not in response.text
    assert db_session.scalar(select(func.count()).select_from(User)) == baseline_users


def test_unrelated_development_user_and_role_survive_registration_rollback(
    db_session: Session,
) -> None:
    baseline_users = int(db_session.scalar(select(func.count()).select_from(User)) or 0)
    baseline_roles = int(db_session.scalar(select(func.count()).select_from(UserRole)) or 0)
    db_session.commit()
    unrelated_email = unique_email("unrelated")

    with db_session.begin():
        unrelated = UserRepository().create(
            db_session,
            email=unrelated_email,
            phone_number=None,
            password_hash="test-only-non-raw-password-digest",
        )
        unrelated_role = UserRoleRepository().create_role(
            db_session,
            user_id=unrelated.id,
            role=UserRoleType.BUYER,
        )

    service = build_registration_service(role_repository=FailingRoleRepository())
    failing_email = unique_email("rollback-target")
    with pytest.raises(RuntimeError):
        service.register(
            db_session,
            RegisterRequest(
                email=failing_email,
                phone_number=unique_phone(),
                password=STRONG_PASSWORD,
            ),
        )

    assert db_session.get(User, unrelated.id) is not None
    assert db_session.get(UserRole, unrelated_role.id) is not None
    assert get_user_by_email(db_session, failing_email) is None
    assert db_session.scalar(select(func.count()).select_from(User)) == baseline_users + 1
    assert db_session.scalar(select(func.count()).select_from(UserRole)) == baseline_roles + 1
