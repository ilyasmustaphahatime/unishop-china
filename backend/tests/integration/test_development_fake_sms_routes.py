from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_phone_verification_service,
    get_registration_service,
)
from app.core.config import Settings, UnsafeRuntimeConfigurationError
from app.core.database import get_db
from app.integrations.development_fake_sms import (
    DevelopmentFakeSmsSender,
    DevelopmentFakeSmsStore,
)
from app.main import create_app
from app.models import PhoneVerificationCode, User
from app.models.base import utc_now
from app.services.auth_service import RegistrationService
from app.services.phone_verification_service import PhoneVerificationService

SECRET = "phase-3b-test-only-verification-secret-with-adequate-entropy"
JWT_TEST_SECRET = "phase-4a-test-only-jwt-secret-with-more-than-thirty-two-characters"
PASSWORD = "StrongPassword123"


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime.now(timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def unique_phone() -> str:
    return f"+86138{uuid4().int % 100_000_000:08d}"


def development_config(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "sms_enabled": True,
        "sms_provider": "fake",
        "enable_fake_sms_dev_inbox": True,
        "fake_sms_localhost_only": True,
        "jwt_secret_key": JWT_TEST_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock()


@pytest.fixture
def store(clock: MutableClock) -> DevelopmentFakeSmsStore:
    return DevelopmentFakeSmsStore(
        delivery_delay_seconds=3,
        ttl_seconds=600,
        max_messages=100,
        now_provider=clock,
    )


@pytest.fixture
def dev_client(
    db_session: Session,
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
) -> Generator[TestClient, None, None]:
    application = create_app(development_config(), fake_sms_store=store)
    sender = DevelopmentFakeSmsSender(store)
    registration = RegistrationService(
        verification_code_hash_secret=SECRET,
        verification_code_generator=lambda: "123456",
        sms_sender=sender,
    )
    verification = PhoneVerificationService(
        verification_code_hash_secret=SECRET,
        verification_code_generator=lambda: "654321",
        sms_sender=sender,
        now_provider=clock,
    )

    def override_db() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_registration_service] = lambda: registration
    application.dependency_overrides[get_phone_verification_service] = lambda: verification
    with TestClient(
        application,
        client=("127.0.0.1", 50000),
        raise_server_exceptions=False,
    ) as client:
        yield client


def register_phone(client: TestClient, phone: str) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/register",
        json={"phone_number": phone, "password": PASSWORD},
    )
    assert response.status_code == 201
    return response.json()


def test_development_route_is_absent_without_explicit_flag() -> None:
    application = create_app(
        development_config(enable_fake_sms_dev_inbox=False, sms_provider="tencent")
    )
    paths = application.openapi()["paths"]
    assert "/api/v1/dev/fake-sms/latest" not in paths


def test_production_route_and_openapi_are_absent() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            app_env="production",
            sms_enabled=False,
            sms_provider="tencent",
            enable_fake_sms_dev_inbox=False,
            jwt_secret_key=JWT_TEST_SECRET,
            verification_code_hash_secret=SECRET,
            refresh_cookie_secure=True,
        )
    )
    assert "/api/v1/dev/fake-sms/latest" not in application.openapi()["paths"]


def test_unsafe_production_fake_configuration_refuses_startup() -> None:
    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(
            Settings(
                _env_file=None,
                app_env="production",
                sms_provider="fake",
                enable_fake_sms_dev_inbox=True,
            )
        )


def test_development_openapi_contains_fake_route(dev_client: TestClient) -> None:
    paths = dev_client.get("/openapi.json").json()["paths"]
    assert "/api/v1/dev/fake-sms/latest" in paths


@pytest.mark.parametrize("client_host", ["127.0.0.1", "::1"])
def test_loopback_clients_may_access_inbox(
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
    client_host: str,
) -> None:
    phone = unique_phone()
    store.add(phone, "123456", "registration")
    clock.advance(3)
    application = create_app(development_config(), fake_sms_store=store)
    with TestClient(application, client=(client_host, 50000)) as client:
        response = client.get("/api/v1/dev/fake-sms/latest", params={"phone_number": phone})
    assert response.status_code == 200


def test_remote_client_and_forged_forwarded_header_are_rejected(
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
) -> None:
    phone = unique_phone()
    store.add(phone, "123456", "registration")
    clock.advance(3)
    application = create_app(development_config(), fake_sms_store=store)
    with TestClient(application, client=("203.0.113.10", 50000)) as client:
        response = client.get(
            "/api/v1/dev/fake-sms/latest",
            params={"phone_number": phone},
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
    assert response.status_code == 403
    assert "123456" not in response.text


def test_registration_message_obeys_delay_masking_and_no_store(
    dev_client: TestClient,
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
    db_session: Session,
) -> None:
    phone = unique_phone()
    payload = register_phone(dev_client, phone)
    assert {"otp", "code", "code_hash", "message_id"}.isdisjoint(payload)

    pending = dev_client.get("/api/v1/dev/fake-sms/latest", params={"phone_number": phone})
    assert pending.status_code == 404
    clock.advance(3)
    delivered = dev_client.get("/api/v1/dev/fake-sms/latest", params={"phone_number": phone})
    body = delivered.json()
    assert delivered.status_code == 200
    assert delivered.headers["cache-control"] == "no-store"
    assert delivered.headers["pragma"] == "no-cache"
    assert body["phone_number_masked"].startswith("+86******")
    assert phone not in delivered.text
    assert body["code"] == "123456"
    assert body["delivery_type"] == "registration"
    user = db_session.scalar(select(User).where(User.phone_number == phone))
    assert user is not None
    record = db_session.scalar(
        select(PhoneVerificationCode).where(PhoneVerificationCode.user_id == user.id)
    )
    assert record is not None and record.code_hash != body["code"]
    assert store.message_count() == 1


def test_successful_verification_consumes_only_matching_message(
    dev_client: TestClient,
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
    db_session: Session,
) -> None:
    phone = unique_phone()
    other_phone = unique_phone()
    register_phone(dev_client, phone)
    store.add(other_phone, "999999", "registration")
    clock.advance(3)

    verified = dev_client.post(
        "/api/v1/auth/phone/verify",
        json={"phone_number": phone, "code": "123456"},
    )

    assert verified.status_code == 200
    assert verified.json()["phone_verified"] is True
    assert store.latest_available(phone) is None
    assert store.latest_available(other_phone) is not None
    user = db_session.scalar(select(User).where(User.phone_number == phone))
    assert user is not None and user.phone_verified is True
    record = db_session.scalar(
        select(PhoneVerificationCode).where(PhoneVerificationCode.user_id == user.id)
    )
    assert record is not None and record.verified_at is not None


def test_wrong_code_leaves_fake_message_available(
    dev_client: TestClient,
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
) -> None:
    phone = unique_phone()
    register_phone(dev_client, phone)
    clock.advance(3)
    response = dev_client.post(
        "/api/v1/auth/phone/verify",
        json={"phone_number": phone, "code": "000000"},
    )
    assert response.status_code == 400
    assert store.latest_available(phone) is not None


def test_resend_supersedes_old_message_and_old_code_fails(
    dev_client: TestClient,
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
    db_session: Session,
) -> None:
    phone = unique_phone()
    register_phone(dev_client, phone)
    first = db_session.scalar(
        select(PhoneVerificationCode)
        .where(PhoneVerificationCode.phone_number == phone)
        .order_by(PhoneVerificationCode.created_at.desc())
        .limit(1)
    )
    assert first is not None
    first.created_at = utc_now() - timedelta(seconds=61)
    db_session.commit()
    clock.advance(61)

    resend = dev_client.post("/api/v1/auth/phone/resend-code", json={"phone_number": phone})
    assert resend.status_code == 202
    assert {"otp", "code", "code_hash", "message_id"}.isdisjoint(resend.json())
    assert store.latest_available(phone) is None
    clock.advance(3)
    latest = store.latest_available(phone)
    assert latest is not None
    assert latest.code == "654321"
    assert latest.delivery_type == "resend"
    old = dev_client.post(
        "/api/v1/auth/phone/verify",
        json={"phone_number": phone, "code": "123456"},
    )
    new = dev_client.post(
        "/api/v1/auth/phone/verify",
        json={"phone_number": phone, "code": "654321"},
    )
    assert old.status_code == 400
    assert new.status_code == 200


def test_unknown_and_verified_phones_create_no_new_fake_message(
    dev_client: TestClient,
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
) -> None:
    unknown_phone = unique_phone()
    unknown = dev_client.post(
        "/api/v1/auth/phone/resend-code",
        json={"phone_number": unknown_phone},
    )
    assert unknown.status_code == 202
    assert store.message_count() == 0

    phone = unique_phone()
    register_phone(dev_client, phone)
    clock.advance(3)
    verified = dev_client.post(
        "/api/v1/auth/phone/verify",
        json={"phone_number": phone, "code": "123456"},
    )
    assert verified.status_code == 200
    resend = dev_client.post(
        "/api/v1/auth/phone/resend-code",
        json={"phone_number": phone},
    )
    assert resend.status_code == 202
    assert store.message_count() == 0


def test_expired_memory_message_is_not_returned(
    store: DevelopmentFakeSmsStore,
    clock: MutableClock,
) -> None:
    phone = unique_phone()
    store.add(phone, "123456", "registration")
    clock.advance(601)
    application = create_app(development_config(), fake_sms_store=store)
    with TestClient(application, client=("127.0.0.1", 50000)) as client:
        response = client.get("/api/v1/dev/fake-sms/latest", params={"phone_number": phone})
    assert response.status_code == 404


def test_unknown_query_parameter_is_rejected(
    dev_client: TestClient,
) -> None:
    response = dev_client.get(
        "/api/v1/dev/fake-sms/latest",
        params={"phone_number": unique_phone(), "user_id": "not-allowed"},
    )
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_missing_phone_query_is_rejected_without_caching(
    dev_client: TestClient,
) -> None:
    response = dev_client.get("/api/v1/dev/fake-sms/latest")

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
