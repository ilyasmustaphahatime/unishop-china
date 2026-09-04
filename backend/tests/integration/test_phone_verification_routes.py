from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_phone_verification_service,
    get_registration_service,
)
from app.common.enums import AccountStatus
from app.core.database import get_db
from app.integrations.sms_client import FakeSmsSender
from app.main import app
from app.models import PhoneVerificationCode, User
from app.models.base import utc_now
from app.services.auth_service import RegistrationService
from app.services.phone_verification_service import PhoneVerificationService
from app.repositories.phone_verification_code_repository import (
    PhoneVerificationCodeRepository,
)
from app.repositories.user_repository import UserRepository

SECRET = "phase-3-integration-secret-with-sufficient-random-looking-entropy"
PHONE = "+8613800000000"
PASSWORD = "StrongPassword123"


@pytest.fixture
def fake_sender() -> FakeSmsSender:
    return FakeSmsSender()


@pytest.fixture
def client(db_session: Session, fake_sender: FakeSmsSender) -> Generator[TestClient, None, None]:
    registration = RegistrationService(
        verification_code_hash_secret=SECRET,
        verification_code_generator=lambda: "123456",
        sms_sender=fake_sender,
    )
    verification = PhoneVerificationService(
        verification_code_hash_secret=SECRET,
        verification_code_generator=lambda: "654321",
        sms_sender=fake_sender,
    )

    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_registration_service] = lambda: registration
    app.dependency_overrides[get_phone_verification_service] = lambda: verification
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register_phone(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={"phone_number": PHONE, "password": PASSWORD},
    )
    assert response.status_code == 201
    return response.json()


def latest_code(db_session: Session) -> PhoneVerificationCode:
    record = db_session.scalar(
        select(PhoneVerificationCode)
        .where(PhoneVerificationCode.phone_number == PHONE)
        .order_by(PhoneVerificationCode.created_at.desc(), PhoneVerificationCode.id.desc())
        .limit(1)
    )
    assert record is not None
    return record


def test_phone_registration_sends_after_commit_and_exposes_no_code(
    client: TestClient, fake_sender: FakeSmsSender, db_session: Session
) -> None:
    payload = register_phone(client)

    assert fake_sender.deliveries == [(PHONE, "123456")]
    assert {"code", "otp", "code_hash"}.isdisjoint(payload)
    record = latest_code(db_session)
    assert record.code_hash != "123456"


def test_email_registration_never_calls_sender(
    client: TestClient, fake_sender: FakeSmsSender
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "phase3@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201
    assert fake_sender.deliveries == []


def test_registration_provider_failure_keeps_user_and_expires_code(
    client: TestClient, fake_sender: FakeSmsSender, db_session: Session
) -> None:
    fake_sender.fail = True
    payload = register_phone(client)
    assert payload["phone_verified"] is False
    user = db_session.scalar(select(User).where(User.phone_number == PHONE))
    assert user is not None
    assert latest_code(db_session).expires_at <= utc_now().replace(tzinfo=None)


def test_newest_code_verifies_and_marks_user_and_code(
    client: TestClient, fake_sender: FakeSmsSender, db_session: Session
) -> None:
    register_phone(client)

    response = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "123456"}
    )

    assert response.status_code == 200
    assert response.json()["phone_verified"] is True
    user = db_session.scalar(select(User).where(User.phone_number == PHONE))
    assert user is not None and user.phone_verified is True
    assert latest_code(db_session).verified_at is not None
    assert len(fake_sender.deliveries) == 1


def test_already_verified_is_idempotent(client: TestClient) -> None:
    register_phone(client)
    first = client.post("/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "123456"})
    second = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "000000"}
    )
    assert first.status_code == second.status_code == 200


def test_wrong_code_increments_attempts(client: TestClient, db_session: Session) -> None:
    register_phone(client)
    response = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "000000"}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_VERIFICATION_CODE"
    assert latest_code(db_session).attempts == 1


def test_fifth_wrong_code_blocks_attempts(client: TestClient) -> None:
    register_phone(client)
    responses = [
        client.post(
            "/api/v1/auth/phone/verify",
            json={"phone_number": PHONE, "code": "000000"},
        )
        for _ in range(5)
    ]
    assert [response.status_code for response in responses] == [400, 400, 400, 400, 429]
    assert responses[-1].json()["detail"]["code"] == "VERIFICATION_ATTEMPTS_EXCEEDED"


def test_expired_code_is_gone_without_attempt_increment(
    client: TestClient, db_session: Session
) -> None:
    register_phone(client)
    record = latest_code(db_session)
    record.expires_at = utc_now() - timedelta(seconds=1)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "123456"}
    )
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "VERIFICATION_CODE_EXPIRED"
    db_session.refresh(record)
    assert record.attempts == 0


def test_resend_enforces_cooldown_without_provider_call(
    client: TestClient, fake_sender: FakeSmsSender
) -> None:
    register_phone(client)
    response = client.post("/api/v1/auth/phone/resend-code", json={"phone_number": PHONE})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert len(fake_sender.deliveries) == 1


def test_resend_creates_new_code_and_old_code_fails(
    client: TestClient, fake_sender: FakeSmsSender, db_session: Session
) -> None:
    register_phone(client)
    first = latest_code(db_session)
    first.created_at = utc_now() - timedelta(seconds=61)
    db_session.commit()

    resend = client.post("/api/v1/auth/phone/resend-code", json={"phone_number": PHONE})
    old = client.post("/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "123456"})
    newest = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "654321"}
    )

    assert resend.status_code == 202
    assert old.status_code == 400
    assert newest.status_code == 200
    assert fake_sender.deliveries[-1] == (PHONE, "654321")


def test_unknown_phone_resend_and_verify_do_not_enumerate(
    client: TestClient, fake_sender: FakeSmsSender
) -> None:
    resend = client.post("/api/v1/auth/phone/resend-code", json={"phone_number": PHONE})
    verify = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "123456"}
    )
    assert resend.status_code == 202
    assert verify.status_code == 400
    assert verify.json()["detail"]["code"] == "INVALID_VERIFICATION_CODE"
    assert fake_sender.deliveries == []


def test_already_verified_phone_resend_does_not_call_sender(
    client: TestClient, fake_sender: FakeSmsSender
) -> None:
    register_phone(client)
    verified = client.post(
        "/api/v1/auth/phone/verify", json={"phone_number": PHONE, "code": "123456"}
    )
    resend = client.post("/api/v1/auth/phone/resend-code", json={"phone_number": PHONE})
    assert verified.status_code == 200
    assert resend.status_code == 202
    assert len(fake_sender.deliveries) == 1


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED],
)
def test_inactive_accounts_cannot_resend_or_complete_phone_verification(
    client: TestClient,
    fake_sender: FakeSmsSender,
    db_session: Session,
    account_status: AccountStatus,
) -> None:
    register_phone(client)
    user = db_session.scalar(select(User).where(User.phone_number == PHONE))
    assert user is not None
    user.account_status = account_status
    db_session.commit()
    delivery_count = len(fake_sender.deliveries)

    resend = client.post(
        "/api/v1/auth/phone/resend-code",
        json={"phone_number": PHONE},
    )
    verification = client.post(
        "/api/v1/auth/phone/verify",
        json={"phone_number": PHONE, "code": "123456"},
    )

    assert resend.status_code == 202
    assert verification.status_code == 400
    assert verification.json()["detail"]["code"] == "INVALID_VERIFICATION_CODE"
    assert len(fake_sender.deliveries) == delivery_count
    db_session.refresh(user)
    assert user.phone_verified is False


def test_provider_failure_expires_exact_resend_record(
    client: TestClient, fake_sender: FakeSmsSender, db_session: Session
) -> None:
    register_phone(client)
    first = latest_code(db_session)
    first.created_at = utc_now() - timedelta(seconds=61)
    db_session.commit()
    fake_sender.fail = True

    response = client.post("/api/v1/auth/phone/resend-code", json={"phone_number": PHONE})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "SMS_PROVIDER_UNAVAILABLE"
    failed_record = latest_code(db_session)
    assert failed_record.id != first.id
    assert failed_record.expires_at <= utc_now().replace(tzinfo=None)


def test_hourly_limit_counts_initial_registration_code(
    client: TestClient, db_session: Session
) -> None:
    register_phone(client)
    user = db_session.scalar(select(User).where(User.phone_number == PHONE))
    assert user is not None
    first = latest_code(db_session)
    first.created_at = utc_now() - timedelta(minutes=30)
    for index in range(4):
        db_session.add(
            PhoneVerificationCode(
                user_id=user.id,
                phone_number=PHONE,
                code_hash=f"test-hash-{index}",
                created_at=utc_now() - timedelta(minutes=index + 2),
                expires_at=utc_now() + timedelta(minutes=5),
            )
        )
    db_session.commit()

    response = client.post("/api/v1/auth/phone/resend-code", json={"phone_number": PHONE})
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "VERIFICATION_CODE_RATE_LIMITED"


def test_openapi_contains_exact_auth_paths(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/register" in paths
    assert "/api/v1/auth/phone/resend-code" in paths
    assert "/api/v1/auth/phone/verify" in paths
    assert all("/auth/auth/" not in path for path in paths)


def test_code_update_failure_rolls_back_user_verification(
    client: TestClient, db_session: Session, fake_sender: FakeSmsSender
) -> None:
    class FailingCodeRepository(PhoneVerificationCodeRepository):
        def mark_verified(self, code: PhoneVerificationCode, verified_at: object) -> None:
            raise RuntimeError("simulated update failure")

    register_phone(client)
    service = PhoneVerificationService(
        sms_sender=fake_sender,
        verification_code_hash_secret=SECRET,
        phone_code_repository=FailingCodeRepository(),
    )
    with pytest.raises(RuntimeError, match="simulated update failure"):
        service.verify(db_session, PHONE, "123456")
    user = db_session.scalar(select(User).where(User.phone_number == PHONE))
    assert user is not None and user.phone_verified is False
    assert latest_code(db_session).verified_at is None


def test_user_update_failure_rolls_back_code_verification(
    client: TestClient, db_session: Session, fake_sender: FakeSmsSender
) -> None:
    class FailingUserRepository(UserRepository):
        def mark_phone_verified(self, user: User) -> None:
            raise RuntimeError("simulated user update failure")

    register_phone(client)
    service = PhoneVerificationService(
        sms_sender=fake_sender,
        verification_code_hash_secret=SECRET,
        user_repository=FailingUserRepository(),
    )
    with pytest.raises(RuntimeError, match="simulated user update failure"):
        service.verify(db_session, PHONE, "123456")
    user = db_session.scalar(select(User).where(User.phone_number == PHONE))
    assert user is not None and user.phone_verified is False
    assert latest_code(db_session).verified_at is None
