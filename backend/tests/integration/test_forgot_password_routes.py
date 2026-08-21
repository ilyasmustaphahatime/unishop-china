from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_forgot_password_identifier_rate_limiter,
    get_forgot_password_ip_rate_limiter,
    get_password_reset_service,
)
from app.common.enums import AccountStatus
from app.core.config import Settings
from app.core.database import get_db
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import verify_password_reset_code
from app.integrations.password_reset_delivery import PasswordResetDeliveryResult
from app.main import app
from app.models import PasswordResetCode, User
from app.repositories.password_reset_code_repository import PasswordResetCodeRepository
from app.services.password_reset_service import (
    DUMMY_PASSWORD_RESET_USER_ID,
    GENERIC_FORGOT_PASSWORD_MESSAGE,
    PasswordResetRequestService,
)

TEST_JWT_SECRET = "phase-5a-test-jwt-secret-with-more-than-thirty-two-characters"
TEST_CODE_SECRET = "phase-5a-test-code-secret-with-more-than-thirty-two-characters"
GENERIC_RESPONSE = {"message": GENERIC_FORGOT_PASSWORD_MESSAGE}


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class CaptureDeliveryProvider:
    enabled = True
    available = True

    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str, str, datetime]] = []
        self.fail = False
        self.confirm_delivery = True

    def deliver_reset_code(
        self,
        *,
        identifier: str,
        identifier_kind: str,
        code: str,
        expires_at: datetime,
    ) -> PasswordResetDeliveryResult:
        self.deliveries.append((identifier, identifier_kind, code, expires_at))
        if self.fail:
            raise RuntimeError("simulated provider failure")
        return PasswordResetDeliveryResult(
            delivered=self.confirm_delivery,
            provider="capture",
            request_id="safe-test-reference",
        )


def reset_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
        "password_reset_delivery_provider": "fake",
        "password_reset_code_expiry_minutes": 10,
        "password_reset_cooldown_seconds": 60,
        "password_reset_hourly_limit_requests": 5,
    }
    values.update(overrides)
    return Settings(**values)


def unlimited_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_requests=1000, window_seconds=3600, max_keys=1000)


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def create_user(
    session: Session,
    *,
    email: str | None = None,
    phone: str | None = None,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=email,
        phone_number=phone,
        password_hash="not-used-by-password-reset-request-tests",
        account_status=status,
    )
    session.add(user)
    session.flush()
    return user


def reset_records(session: Session, user: User) -> list[PasswordResetCode]:
    return list(
        session.scalars(
            select(PasswordResetCode)
            .where(PasswordResetCode.user_id == user.id)
            .order_by(PasswordResetCode.created_at, PasswordResetCode.id)
        )
    )


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime.now(timezone.utc).replace(microsecond=0))


@pytest.fixture
def provider() -> CaptureDeliveryProvider:
    return CaptureDeliveryProvider()


@pytest.fixture
def service(
    clock: MutableClock,
    provider: CaptureDeliveryProvider,
) -> PasswordResetRequestService:
    return PasswordResetRequestService(
        reset_settings(),
        delivery_provider=provider,
        code_generator=lambda: "123456",
        now_provider=clock,
    )


@pytest.fixture
def client(
    db_session: Session,
    service: PasswordResetRequestService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_password_reset_service] = lambda: service
    app.dependency_overrides[get_forgot_password_ip_rate_limiter] = unlimited_limiter
    app.dependency_overrides[get_forgot_password_identifier_rate_limiter] = (
        unlimited_limiter
    )
    try:
        with TestClient(
            app,
            client=("198.51.100.42", 51000),
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def assert_generic(response) -> None:
    assert response.status_code == 202
    assert response.json() == GENERIC_RESPONSE
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_existing_email_creates_only_a_hash_and_returns_generic_response(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    email = unique_email("existing")
    user = create_user(db_session, email=email)

    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": f"  {email.upper()}  "},
    )

    assert_generic(response)
    records = reset_records(db_session, user)
    assert len(records) == 1
    record = records[0]
    assert record.used_at is None
    assert record.code_hash != "123456"
    assert verify_password_reset_code("123456", record.code_hash, TEST_CODE_SECRET)
    assert record.expires_at.replace(tzinfo=timezone.utc) == clock.now + timedelta(
        minutes=10
    )
    assert provider.deliveries[0][:3] == (email, "email", "123456")
    assert "123456" not in response.text


@pytest.mark.parametrize("submitted", ["13800000000", "0086 13800000000"])
def test_china_phone_formats_are_normalized_before_delivery(
    submitted: str,
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    user = create_user(db_session, phone="+8613800000000")

    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": submitted},
    )

    assert_generic(response)
    assert len(reset_records(db_session, user)) == 1
    assert provider.deliveries[0][:2] == ("+8613800000000", "phone")


@pytest.mark.parametrize("identifier", ["missing@example.com", "+8613900000000"])
def test_unknown_identifier_is_indistinguishable_and_creates_no_row(
    identifier: str,
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    before = int(
        db_session.scalar(select(func.count()).select_from(PasswordResetCode)) or 0
    )

    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": identifier},
    )

    assert_generic(response)
    assert (
        db_session.scalar(select(func.count()).select_from(PasswordResetCode)) == before
    )
    assert provider.deliveries == []


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED],
)
def test_inactive_accounts_receive_generic_response_without_delivery(
    account_status: AccountStatus,
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    user = create_user(
        db_session,
        email=unique_email(account_status.value.lower()),
        status=account_status,
    )

    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": user.email},
    )

    assert_generic(response)
    assert reset_records(db_session, user) == []
    assert provider.deliveries == []


def test_cooldown_suppresses_repeat_then_replaces_the_old_active_code(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("cooldown"))

    assert_generic(
        client.post(
            "/api/v1/auth/password/forgot", json={"identifier": user.email}
        )
    )
    assert_generic(
        client.post(
            "/api/v1/auth/password/forgot", json={"identifier": user.email}
        )
    )
    assert len(reset_records(db_session, user)) == 1
    assert len(provider.deliveries) == 1

    clock.advance(61)
    assert_generic(
        client.post(
            "/api/v1/auth/password/forgot", json={"identifier": user.email}
        )
    )

    records = reset_records(db_session, user)
    assert len(records) == 2
    assert records[0].used_at is not None
    assert records[1].used_at is None
    assert len(provider.deliveries) == 2


def test_database_rolling_hour_limit_is_enforced(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("hourly"))

    for _ in range(5):
        assert_generic(
            client.post(
                "/api/v1/auth/password/forgot", json={"identifier": user.email}
            )
        )
        clock.advance(61)
    assert_generic(
        client.post(
            "/api/v1/auth/password/forgot", json={"identifier": user.email}
        )
    )

    records = reset_records(db_session, user)
    assert len(records) == 5
    assert len(provider.deliveries) == 5
    assert sum(record.used_at is None for record in records) == 1


@pytest.mark.parametrize("failure_mode", ["raise", "unconfirmed"])
def test_provider_failure_never_activates_an_undelivered_code(
    failure_mode: str,
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    user = create_user(db_session, email=unique_email("provider-failure"))
    provider.fail = failure_mode == "raise"
    provider.confirm_delivery = failure_mode != "unconfirmed"

    response = client.post(
        "/api/v1/auth/password/forgot", json={"identifier": user.email}
    )

    assert_generic(response)
    records = reset_records(db_session, user)
    assert len(records) == 1
    assert records[0].used_at is not None
    assert len(provider.deliveries) == 1


def test_activation_failure_stays_generic_and_leaves_pending_code_inactive(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    class ActivationFailureRepository(PasswordResetCodeRepository):
        def activate_pending(self, session: Session, *, code_id: str) -> int:
            raise RuntimeError("simulated activation failure")

    user = create_user(db_session, email=unique_email("activation-failure"))
    failing_service = PasswordResetRequestService(
        reset_settings(),
        delivery_provider=provider,
        reset_repository=ActivationFailureRepository(),
        code_generator=lambda: "123456",
        now_provider=clock,
    )
    app.dependency_overrides[get_password_reset_service] = lambda: failing_service

    response = client.post(
        "/api/v1/auth/password/forgot", json={"identifier": user.email}
    )

    assert_generic(response)
    assert reset_records(db_session, user)[0].used_at is not None
    assert len(provider.deliveries) == 1


def test_delayed_delivery_cannot_activate_an_older_pending_code(
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("delayed-delivery"))

    class NewerChallengeDuringDelivery(CaptureDeliveryProvider):
        def deliver_reset_code(
            self,
            *,
            identifier: str,
            identifier_kind: str,
            code: str,
            expires_at: datetime,
        ) -> PasswordResetDeliveryResult:
            result = super().deliver_reset_code(
                identifier=identifier,
                identifier_kind=identifier_kind,
                code=code,
                expires_at=expires_at,
            )
            newer_at = clock.now + timedelta(seconds=1)
            db_session.add(
                PasswordResetCode(
                    user_id=user.id,
                    code_hash="newer-pending-hash",
                    created_at=newer_at,
                    expires_at=newer_at + timedelta(minutes=10),
                    used_at=newer_at,
                )
            )
            db_session.flush()
            return result

    racing_provider = NewerChallengeDuringDelivery()
    reset_service = PasswordResetRequestService(
        reset_settings(),
        delivery_provider=racing_provider,
        code_generator=lambda: "123456",
        now_provider=clock,
    )

    result = reset_service.request_reset(
        db_session,
        identifier=user.email or "",
        identifier_kind="email",
    )

    records = reset_records(db_session, user)
    assert result.message == GENERIC_FORGOT_PASSWORD_MESSAGE
    assert len(records) == 2
    assert all(record.used_at is not None for record in records)


def test_insert_failure_rolls_back_old_code_invalidation(
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    class InsertFailureRepository(PasswordResetCodeRepository):
        def create_pending(self, *args: object, **kwargs: object) -> PasswordResetCode:
            raise RuntimeError("simulated insert failure")

    user = create_user(db_session, email=unique_email("rollback"))
    old = PasswordResetCode(
        user_id=user.id,
        code_hash="existing-hash",
        created_at=clock.now - timedelta(minutes=2),
        expires_at=clock.now + timedelta(minutes=8),
        used_at=None,
    )
    db_session.add(old)
    db_session.flush()
    failing_service = PasswordResetRequestService(
        reset_settings(),
        delivery_provider=provider,
        reset_repository=InsertFailureRepository(),
        code_generator=lambda: "123456",
        now_provider=clock,
    )

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        failing_service.request_reset(
            db_session,
            identifier=user.email or "",
            identifier_kind="email",
        )

    db_session.refresh(old)
    assert old.used_at is None
    assert len(reset_records(db_session, user)) == 1
    assert provider.deliveries == []


def test_old_code_invalidation_failure_creates_no_partial_challenge(
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    class InvalidationFailureRepository(PasswordResetCodeRepository):
        def invalidate_active_for_user(self, *args: object, **kwargs: object) -> int:
            raise RuntimeError("simulated invalidation failure")

    user = create_user(db_session, email=unique_email("invalidation-rollback"))
    old = PasswordResetCode(
        user_id=user.id,
        code_hash="existing-hash",
        created_at=clock.now - timedelta(minutes=2),
        expires_at=clock.now + timedelta(minutes=8),
        used_at=None,
    )
    db_session.add(old)
    db_session.flush()
    failing_service = PasswordResetRequestService(
        reset_settings(),
        delivery_provider=provider,
        reset_repository=InvalidationFailureRepository(),
        code_generator=lambda: "123456",
        now_provider=clock,
    )

    with pytest.raises(RuntimeError, match="simulated invalidation failure"):
        failing_service.request_reset(
            db_session,
            identifier=user.email or "",
            identifier_kind="email",
        )

    db_session.refresh(old)
    assert old.used_at is None
    assert len(reset_records(db_session, user)) == 1
    assert provider.deliveries == []


def test_ip_rate_limit_uses_connection_peer_and_ignores_forwarded_header(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_forgot_password_ip_rate_limiter] = lambda: limiter

    first = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": unique_email("first")},
    )
    blocked = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": unique_email("second")},
        headers={"X-Forwarded-For": "203.0.113.200"},
    )

    assert_generic(first)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["cache-control"] == "no-store"
    assert list(limiter._requests) == ["198.51.100.42"]
    assert provider.deliveries == []
    assert db_session.scalar(select(func.count()).select_from(PasswordResetCode)) == 0


def test_identifier_rate_limit_uses_normalized_hmac_key(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_forgot_password_identifier_rate_limiter] = (
        lambda: limiter
    )
    email = unique_email("identifier-limit")
    user = create_user(db_session, email=email)

    first = client.post(
        "/api/v1/auth/password/forgot", json={"identifier": email.upper()}
    )
    blocked = client.post(
        "/api/v1/auth/password/forgot", json={"identifier": f" {email} "}
    )

    assert_generic(first)
    assert blocked.status_code == 429
    assert len(limiter._requests) == 1
    assert email not in next(iter(limiter._requests))
    assert len(reset_records(db_session, user)) == 1
    assert len(provider.deliveries) == 1


def test_cross_origin_and_invalid_payloads_have_no_side_effects(
    client: TestClient,
    db_session: Session,
    provider: CaptureDeliveryProvider,
) -> None:
    user = create_user(db_session, email=unique_email("negative"))

    foreign = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": user.email},
        headers={"Origin": "https://attacker.example"},
    )
    invalid = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": user.email, "user_id": user.id, "code": "123456"},
    )
    oversized = client.post(
        "/api/v1/auth/password/forgot", json={"identifier": "a" * 256}
    )

    assert foreign.status_code == 403
    assert invalid.status_code == oversized.status_code == 422
    assert reset_records(db_session, user) == []
    assert provider.deliveries == []


def test_route_masks_unexpected_service_failure(
    client: TestClient,
    db_session: Session,
) -> None:
    class FailingService:
        def request_reset(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("internal-only failure")

    app.dependency_overrides[get_password_reset_service] = lambda: FailingService()

    response = client.post(
        "/api/v1/auth/password/forgot",
        json={"identifier": unique_email("service-failure")},
    )

    assert_generic(response)
    assert "internal-only failure" not in response.text
    assert db_session.scalar(select(func.count()).select_from(PasswordResetCode)) == 0


def test_unknown_identifier_executes_dummy_database_workload(
    db_session: Session,
    provider: CaptureDeliveryProvider,
    clock: MutableClock,
) -> None:
    class RecordingRepository(PasswordResetCodeRepository):
        def __init__(self) -> None:
            self.user_ids: list[str] = []

        def get_latest_for_user(
            self, session: Session, user_id: str, *, for_update: bool = False
        ) -> PasswordResetCode | None:
            self.user_ids.append(user_id)
            return super().get_latest_for_user(
                session, user_id, for_update=for_update
            )

        def count_created_since(
            self, session: Session, *, user_id: str, since: datetime
        ) -> int:
            self.user_ids.append(user_id)
            return super().count_created_since(session, user_id=user_id, since=since)

    repository = RecordingRepository()
    reset_service = PasswordResetRequestService(
        reset_settings(),
        delivery_provider=provider,
        reset_repository=repository,
        code_generator=lambda: "123456",
        now_provider=clock,
    )

    result = reset_service.request_reset(
        db_session,
        identifier=unique_email("unknown-workload"),
        identifier_kind="email",
    )

    assert result.message == GENERIC_FORGOT_PASSWORD_MESSAGE
    assert repository.user_ids == [
        DUMMY_PASSWORD_RESET_USER_ID,
        DUMMY_PASSWORD_RESET_USER_ID,
    ]
    assert provider.deliveries == []


def test_openapi_contains_only_the_phase_5a_password_recovery_route() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/password/forgot" in paths
    assert "post" in paths["/api/v1/auth/password/forgot"]
    assert "/api/v1/auth/password/reset" not in paths
    assert not any("email/verify" in path for path in paths)
