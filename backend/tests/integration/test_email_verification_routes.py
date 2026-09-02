import json
import secrets
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Lock
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_access_token_service,
    get_email_verification_resend_ip_rate_limiter,
    get_email_verification_resend_user_rate_limiter,
    get_email_verification_service,
    get_email_verification_verify_ip_rate_limiter,
    get_email_verification_verify_user_rate_limiter,
)
from app.common.enums import AccountStatus, UserRoleType
from app.core.config import Settings
from app.core.database import engine, get_db
from app.core.exceptions import EmailVerificationError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_email_verification_code, hash_password
from app.core.session_security import hash_csrf_token, hash_refresh_token
from app.integrations.email_verification_delivery import (
    DevelopmentFakeEmailVerificationStore,
    EmailVerificationDeliveryResult,
)
from app.main import app, create_app
from app.models import EmailVerificationCode, RefreshToken, User, UserRole
from app.models.base import utc_now
from app.repositories.email_verification_code_repository import (
    EmailVerificationCodeRepository,
)
from app.services.email_verification_service import (
    EMAIL_VERIFIED_MESSAGE,
    GENERIC_EMAIL_RESEND_MESSAGE,
    GENERIC_INVALID_EMAIL_VERIFICATION_MESSAGE,
    EmailVerificationService,
)
from app.services.token_service import AccessTokenService

TEST_JWT_SECRET = "phase-5d-test-jwt-secret-with-more-than-thirty-two-characters"
TEST_CODE_SECRET = "phase-5d-test-code-secret-with-more-than-thirty-two-characters"
VALID_CODE = "123456"
WRONG_CODE = "000000"
ORIGIN = "http://localhost:5173"


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class CaptureProvider:
    enabled = True
    available = True

    def __init__(self) -> None:
        self.deliveries: list[tuple[str, str, str, datetime]] = []
        self.consumed: list[tuple[str, str]] = []
        self.fail = False
        self.confirm_delivery = True
        self._lock = Lock()

    def deliver_verification_code(
        self,
        *,
        user_id: str,
        email: str,
        code: str,
        expires_at: datetime,
    ) -> EmailVerificationDeliveryResult:
        with self._lock:
            self.deliveries.append((user_id, email, code, expires_at))
        if self.fail:
            raise RuntimeError("simulated provider failure")
        return EmailVerificationDeliveryResult(
            delivered=self.confirm_delivery,
            provider="capture",
            request_id="safe-test-reference",
        )

    def consume_verification_code(self, *, user_id: str, code: str) -> None:
        with self._lock:
            self.consumed.append((user_id, code))


class BlockingProvider(CaptureProvider):
    def __init__(self) -> None:
        super().__init__()
        self.delivery_started = Event()
        self.release_delivery = Event()

    def deliver_verification_code(
        self,
        *,
        user_id: str,
        email: str,
        code: str,
        expires_at: datetime,
    ) -> EmailVerificationDeliveryResult:
        self.delivery_started.set()
        if not self.release_delivery.wait(timeout=10):
            raise RuntimeError("test delivery release timed out")
        return super().deliver_verification_code(
            user_id=user_id,
            email=email,
            code=code,
            expires_at=expires_at,
        )


def phase_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "app_debug": False,
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
        "jwt_algorithm": "HS256",
        "jwt_issuer": "unishop-china-api",
        "jwt_audience": "unishop-china-web",
        "jwt_clock_skew_seconds": 0,
        "email_verification_delivery_provider": "fake",
        "email_verification_code_expiry_minutes": 10,
        "email_verification_cooldown_seconds": 60,
        "email_verification_hourly_limit_requests": 5,
        "email_verification_max_attempts": 5,
        "frontend_url": ORIGIN,
    }
    values.update(overrides)
    return Settings(**values)


def unlimited_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_requests=1000, window_seconds=3600, max_keys=1000)


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime.now(timezone.utc).replace(microsecond=0))


@pytest.fixture
def provider() -> CaptureProvider:
    return CaptureProvider()


@pytest.fixture
def service(clock: MutableClock, provider: CaptureProvider) -> EmailVerificationService:
    return EmailVerificationService(
        phase_settings(),
        delivery_provider=provider,
        code_generator=lambda: VALID_CODE,
        now_provider=clock,
    )


@pytest.fixture
def token_service() -> AccessTokenService:
    return AccessTokenService(phase_settings())


@pytest.fixture
def client(
    db_session: Session,
    service: EmailVerificationService,
    token_service: AccessTokenService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_token_service] = lambda: token_service
    app.dependency_overrides[get_email_verification_service] = lambda: service
    for dependency in (
        get_email_verification_resend_ip_rate_limiter,
        get_email_verification_resend_user_rate_limiter,
        get_email_verification_verify_ip_rate_limiter,
        get_email_verification_verify_user_rate_limiter,
    ):
        app.dependency_overrides[dependency] = unlimited_limiter
    try:
        with TestClient(
            app,
            client=("198.51.100.77", 56000),
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def unique_email(label: str) -> str:
    return f"phase5d-{label}-{uuid4().hex}@example.com"


def unique_phone() -> str:
    return f"+86139{uuid4().int % 100_000_000:08d}"


def create_user(
    session: Session,
    *,
    label: str,
    email: str | None = None,
    phone: str | None = None,
    email_verified: bool = False,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=email if email is not None else unique_email(label),
        phone_number=phone,
        password_hash=hash_password("SyntheticPhase5DPassword123"),
        email_verified=email_verified,
        account_status=status,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
    session.flush()
    return user


def create_phone_only_user(session: Session, *, label: str) -> User:
    user = User(
        email=None,
        phone_number=unique_phone(),
        password_hash=hash_password("SyntheticPhase5DPassword123"),
        account_status=AccountStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
    session.flush()
    return user


def create_active_challenge(
    session: Session,
    *,
    user: User,
    code: str = VALID_CODE,
    now: datetime | None = None,
    attempts: int = 0,
    used_at: datetime | None = None,
) -> EmailVerificationCode:
    created_at = now or utc_now()
    challenge = EmailVerificationCode(
        user_id=user.id,
        code_hash=hash_email_verification_code(code, TEST_CODE_SECRET),
        expires_at=created_at + timedelta(minutes=10),
        attempts=attempts,
        activated_at=created_at,
        used_at=used_at,
        created_at=created_at,
    )
    session.add(challenge)
    session.flush()
    return challenge


def auth_headers(token_service: AccessTokenService, user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token_service.create_access_token(user.id)}",
        "Origin": ORIGIN,
    }


def resend(client: TestClient, headers: dict[str, str]):
    return client.post(
        "/api/v1/auth/email/resend-code",
        headers=headers,
        json={},
    )


def verify(client: TestClient, headers: dict[str, str], code: str):
    return client.post(
        "/api/v1/auth/email/verify",
        headers=headers,
        json={"code": code},
    )


def test_authenticated_user_can_request_verify_and_read_fresh_me_state(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="happy")
    headers = auth_headers(token_service, user)

    before = client.get("/api/v1/auth/me", headers=headers)
    requested = resend(client, headers)

    assert before.status_code == 200
    assert before.json()["email_verified"] is False
    assert requested.status_code == 202
    assert requested.json() == {
        "message": GENERIC_EMAIL_RESEND_MESSAGE,
        "expires_in_seconds": 600,
    }
    assert requested.headers["cache-control"] == "no-store"
    assert provider.deliveries[0][0:2] == (user.id, user.email)
    raw_code = provider.deliveries[0][2]
    challenge = db_session.scalar(
        select(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )
    assert challenge is not None
    assert challenge.code_hash != raw_code
    assert raw_code not in challenge.code_hash
    assert challenge.activated_at is not None
    assert challenge.used_at is None

    verified = verify(client, headers, raw_code)
    after = client.get("/api/v1/auth/me", headers=headers)

    assert verified.status_code == 200
    assert verified.json() == {
        "message": EMAIL_VERIFIED_MESSAGE,
        "email_verified": True,
    }
    assert verified.headers["cache-control"] == "no-store"
    assert after.status_code == 200
    assert after.json()["email_verified"] is True
    db_session.refresh(challenge)
    assert challenge.used_at is not None
    assert provider.consumed == [(user.id, raw_code)]


def test_wrong_attempts_are_durable_exhaustion_blocks_correct_code(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="attempts")
    headers = auth_headers(token_service, user)
    assert resend(client, headers).status_code == 202
    correct = provider.deliveries[-1][2]

    failures = [verify(client, headers, WRONG_CODE) for _ in range(5)]
    exhausted = verify(client, headers, correct)

    assert all(response.status_code == 400 for response in failures)
    assert exhausted.status_code == 400
    assert exhausted.json()["detail"]["message"] == (
        GENERIC_INVALID_EMAIL_VERIFICATION_MESSAGE
    )
    challenge = db_session.scalar(
        select(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )
    db_session.refresh(user)
    assert challenge is not None and challenge.attempts == 5
    assert challenge.used_at is None
    assert user.email_verified is False


def test_expired_code_is_rejected_without_increment(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, label="expired")
    headers = auth_headers(token_service, user)
    assert resend(client, headers).status_code == 202
    clock.advance(601)

    response = verify(client, headers, provider.deliveries[-1][2])

    challenge = db_session.scalar(
        select(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )
    assert response.status_code == 400
    assert challenge is not None and challenge.attempts == 0
    db_session.refresh(user)
    assert user.email_verified is False


def test_resend_supersedes_old_code_and_replay_is_rejected(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, label="newest")
    headers = auth_headers(token_service, user)
    assert resend(client, headers).status_code == 202
    old_code = provider.deliveries[-1][2]
    clock.advance(61)
    service = app.dependency_overrides[get_email_verification_service]()
    service.code_generator = lambda: "654321"
    assert resend(client, headers).status_code == 202
    new_code = provider.deliveries[-1][2]

    assert verify(client, headers, old_code).status_code == 400
    assert verify(client, headers, new_code).status_code == 200
    replay = verify(client, headers, new_code)

    rows = list(
        db_session.scalars(
            select(EmailVerificationCode)
            .where(EmailVerificationCode.user_id == user.id)
            .order_by(EmailVerificationCode.created_at)
        )
    )
    assert len(rows) == 2
    assert rows[0].used_at is not None
    assert rows[1].used_at is not None
    assert replay.status_code == 400


def test_resend_cooldown_and_rolling_limit_return_retry_after(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, label="resend-limits")
    headers = auth_headers(token_service, user)
    first = resend(client, headers)
    cooldown = resend(client, headers)

    assert first.status_code == 202
    assert cooldown.status_code == 429
    assert int(cooldown.headers["retry-after"]) >= 1

    for _ in range(4):
        clock.advance(61)
        assert resend(client, headers).status_code == 202
    clock.advance(61)
    rolling = resend(client, headers)
    assert rolling.status_code == 429
    assert int(rolling.headers["retry-after"]) >= 1
    count = db_session.scalar(
        select(func.count())
        .select_from(EmailVerificationCode)
        .where(EmailVerificationCode.user_id == user.id)
    )
    assert count == 5


def test_provider_failure_cancels_pending_and_preserves_previous_active_code(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, label="provider-failure")
    headers = auth_headers(token_service, user)
    assert resend(client, headers).status_code == 202
    first = db_session.scalar(
        select(EmailVerificationCode).where(EmailVerificationCode.user_id == user.id)
    )
    assert first is not None and first.used_at is None
    clock.advance(61)
    provider.fail = True

    failed = resend(client, headers)

    assert failed.status_code == 503
    rows = list(
        db_session.scalars(
            select(EmailVerificationCode)
            .where(EmailVerificationCode.user_id == user.id)
            .order_by(EmailVerificationCode.created_at)
        )
    )
    assert len(rows) == 2
    assert rows[0].activated_at is not None and rows[0].used_at is None
    assert rows[1].activated_at is None and rows[1].used_at is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "victim"},
        {"email": "victim@example.com"},
        {"role": "ADMIN"},
        {"status": "ACTIVE"},
        {"email_verified": True},
    ],
)
def test_resend_rejects_mass_assignment_fields(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
    payload: dict[str, object],
) -> None:
    user = create_user(db_session, label="resend-mass")
    response = client.post(
        "/api/v1/auth/email/resend-code",
        headers=auth_headers(token_service, user),
        json=payload,
    )
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["user_id", "email", "role", "status", "phone_verified"])
def test_verify_rejects_mass_assignment_fields(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
    field: str,
) -> None:
    user = create_user(db_session, label="verify-mass")
    response = client.post(
        "/api/v1/auth/email/verify",
        headers=auth_headers(token_service, user),
        json={"code": VALID_CODE, field: "forbidden"},
    )
    assert response.status_code == 422


def test_user_cannot_verify_another_users_challenge(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
) -> None:
    user_a = create_user(db_session, label="cross-a")
    user_b = create_user(db_session, label="cross-b")
    headers_a = auth_headers(token_service, user_a)
    headers_b = auth_headers(token_service, user_b)
    assert resend(client, headers_b).status_code == 202
    code_b = provider.deliveries[-1][2]

    rejected = verify(client, headers_a, code_b)

    assert rejected.status_code == 400
    db_session.refresh(user_a)
    db_session.refresh(user_b)
    assert user_a.email_verified is False
    assert user_b.email_verified is False
    assert verify(client, headers_b, code_b).status_code == 200


def test_no_email_already_verified_and_inactive_accounts_are_safe(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
) -> None:
    no_email = create_phone_only_user(db_session, label="no-email")
    verified_user = create_user(db_session, label="verified", email_verified=True)
    suspended = create_user(
        db_session,
        label="suspended",
        status=AccountStatus.SUSPENDED,
    )

    no_email_headers = auth_headers(token_service, no_email)
    verified_headers = auth_headers(token_service, verified_user)
    suspended_headers = auth_headers(token_service, suspended)

    assert resend(client, no_email_headers).status_code == 202
    assert verify(client, no_email_headers, VALID_CODE).status_code == 400
    assert resend(client, verified_headers).status_code == 202
    assert verify(client, verified_headers, VALID_CODE).status_code == 400
    assert resend(client, suspended_headers).status_code == 401
    assert verify(client, suspended_headers, VALID_CODE).status_code == 401
    assert provider.deliveries == []


def test_http_ip_and_user_rate_limits_use_safe_actual_peer_keys(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="http-rate")
    headers = auth_headers(token_service, user)
    ip_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    user_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_email_verification_resend_ip_rate_limiter] = (
        lambda: ip_limiter
    )
    app.dependency_overrides[get_email_verification_resend_user_rate_limiter] = (
        lambda: user_limiter
    )

    assert resend(client, headers).status_code == 202
    spoofed = resend(
        client,
        {**headers, "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
    )

    assert spoofed.status_code == 429
    assert int(spoofed.headers["retry-after"]) >= 1
    assert set(ip_limiter._requests) == {"198.51.100.77"}
    limiter_key = next(iter(user_limiter._requests))
    assert user.id not in limiter_key
    assert user.email not in limiter_key


def test_verify_http_rate_limit_returns_retry_after(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="verify-rate")
    headers = auth_headers(token_service, user)
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_email_verification_verify_user_rate_limiter] = (
        lambda: limiter
    )

    assert verify(client, headers, WRONG_CODE).status_code == 400
    blocked = verify(client, headers, WRONG_CODE)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1


def test_validation_never_reflects_unicode_code_or_logs_sensitive_input(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = create_user(db_session, label="validation")
    marker = "１２３４５６"
    response = client.post(
        "/api/v1/auth/email/verify",
        headers=auth_headers(token_service, user),
        json={"code": marker},
    )
    serialized = json.dumps(response.json(), ensure_ascii=False)
    assert response.status_code == 422
    assert marker not in serialized
    assert marker not in caplog.text
    assert "input" not in serialized
    assert "ctx" not in serialized
    assert "errors.pydantic.dev" not in serialized


class FailingInvalidationRepository(EmailVerificationCodeRepository):
    def invalidate_active_for_user(self, *args: object, **kwargs: object) -> int:
        raise RuntimeError("simulated transaction failure")


def test_verification_failure_injection_rolls_back_user_and_challenge(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, label="rollback")
    challenge = create_active_challenge(db_session, user=user, now=clock.now)
    failing_service = EmailVerificationService(
        phase_settings(),
        delivery_provider=provider,
        challenge_repository=FailingInvalidationRepository(),
        now_provider=clock,
    )
    app.dependency_overrides[get_email_verification_service] = lambda: failing_service

    response = verify(client, auth_headers(token_service, user), VALID_CODE)

    assert response.status_code == 500
    db_session.expire_all()
    reloaded_user = db_session.get(User, user.id)
    reloaded_challenge = db_session.get(EmailVerificationCode, challenge.id)
    assert reloaded_user is not None and reloaded_user.email_verified is False
    assert reloaded_challenge is not None and reloaded_challenge.used_at is None


def test_email_verification_preserves_roles_phone_password_and_refresh_sessions(
    client: TestClient,
    db_session: Session,
    provider: CaptureProvider,
    token_service: AccessTokenService,
) -> None:
    user = create_user(
        db_session,
        label="preserve",
        phone=unique_phone(),
    )
    original_password_hash = user.password_hash
    raw_refresh = secrets.token_urlsafe(64)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=str(uuid4()),
        csrf_token_hash=hash_csrf_token(secrets.token_urlsafe(32)),
        expires_at=utc_now() + timedelta(days=7),
        family_expires_at=utc_now() + timedelta(days=30),
    )
    db_session.add(refresh)
    db_session.flush()
    headers = auth_headers(token_service, user)
    assert resend(client, headers).status_code == 202
    assert verify(client, headers, provider.deliveries[-1][2]).status_code == 200

    db_session.refresh(user)
    db_session.refresh(refresh)
    roles = list(db_session.scalars(select(UserRole.role).where(UserRole.user_id == user.id)))
    assert user.email_verified is True
    assert user.phone_verified is False
    assert user.account_status is AccountStatus.ACTIVE
    assert user.password_hash == original_password_hash
    assert roles == [UserRoleType.BUYER]
    assert refresh.revoked_at is None


def test_fake_inbox_is_authenticated_owner_scoped_loopback_only_and_not_production(
    db_session: Session,
    token_service: AccessTokenService,
    clock: MutableClock,
) -> None:
    user_a = create_user(db_session, label="fake-a")
    user_b = create_user(db_session, label="fake-b")
    store = DevelopmentFakeEmailVerificationStore(
        user_reference_secret=TEST_JWT_SECRET,
        delivery_delay_seconds=0,
        ttl_seconds=600,
        max_messages=10,
        now_provider=clock,
    )
    store.add(
        user_id=user_a.id,
        code=VALID_CODE,
        expires_at=clock.now + timedelta(minutes=10),
    )
    config = phase_settings(enable_fake_email_verification_dev_inbox=True)
    application = create_app(config, fake_email_verification_store=store)

    def override_db() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_access_token_service] = lambda: token_service
    with TestClient(application, client=("127.0.0.1", 56001)) as local:
        owner = local.get(
            "/api/v1/dev/fake-email/latest",
            headers=auth_headers(token_service, user_a),
        )
        other = local.get(
            "/api/v1/dev/fake-email/latest",
            headers=auth_headers(token_service, user_b),
        )
        assert owner.status_code == 200
        assert owner.json()["code"] == VALID_CODE
        assert user_a.email not in owner.text
        assert other.status_code == 404

    with TestClient(application, client=("198.51.100.50", 56002)) as remote:
        rejected = remote.get(
            "/api/v1/dev/fake-email/latest",
            headers={
                **auth_headers(token_service, user_a),
                "X-Forwarded-For": "127.0.0.1",
                "Forwarded": "for=127.0.0.1",
            },
        )
        assert rejected.status_code == 403

    production = create_app(
        phase_settings(
            app_env="production",
            frontend_url="https://shop.example.test",
            refresh_cookie_secure=True,
            email_verification_delivery_provider="disabled",
            enable_fake_email_verification_dev_inbox=False,
        )
    )
    assert not any("fake-email" in path for path in production.openapi()["paths"])


def test_live_schema_and_openapi_match_phase_5d_contract() -> None:
    inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("email_verification_codes")
    }
    checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("email_verification_codes")
    }
    foreign_keys = inspector.get_foreign_keys("email_verification_codes")
    paths = app.openapi()["paths"]

    assert set(columns) == {
        "user_id",
        "code_hash",
        "expires_at",
        "attempts",
        "activated_at",
        "used_at",
        "id",
        "created_at",
    }
    assert columns["attempts"]["nullable"] is False
    assert "attempts" in checks[
        "ck_email_verification_codes_attempts_non_negative"
    ]
    assert foreign_keys[0]["referred_table"] == "users"
    assert foreign_keys[0]["options"]["ondelete"] == "CASCADE"
    assert "/api/v1/auth/email/resend-code" in paths
    assert "/api/v1/auth/email/verify" in paths
    assert sum(path == "/api/v1/auth/email/resend-code" for path in paths) == 1
    assert sum(path == "/api/v1/auth/email/verify" for path in paths) == 1
    assert not any("phase-5e" in path or "mfa" in path for path in paths)


def database_counts() -> tuple[int, int, int]:
    with Session(engine) as session:
        return (
            int(session.scalar(select(func.count()).select_from(User)) or 0),
            int(session.scalar(select(func.count()).select_from(UserRole)) or 0),
            int(
                session.scalar(
                    select(func.count()).select_from(EmailVerificationCode)
                )
                or 0
            ),
        )


def create_committed_fixture(
    *,
    code: str = VALID_CODE,
    created_at: datetime | None = None,
) -> tuple[str, str]:
    with Session(engine) as session, session.begin():
        user = create_user(session, label="concurrency")
        create_active_challenge(
            session,
            user=user,
            code=code,
            now=created_at,
        )
        return user.id, user.email


def cleanup_committed_user(user_id: str) -> None:
    with Session(engine) as session, session.begin():
        session.execute(delete(User).where(User.id == user_id))


def test_concurrent_valid_verification_has_exactly_one_success() -> None:
    baseline = database_counts()
    user_id, _email = create_committed_fixture()
    barrier = Barrier(2)
    provider = CaptureProvider()

    def attempt() -> str:
        barrier.wait()
        with Session(engine) as session:
            try:
                EmailVerificationService(
                    phase_settings(),
                    delivery_provider=provider,
                ).verify(session, user_id=user_id, submitted_code=VALID_CODE)
            except EmailVerificationError:
                return "invalid"
            return "success"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: attempt(), range(2)))
        assert sorted(outcomes) == ["invalid", "success"]
        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(EmailVerificationCode).where(
                    EmailVerificationCode.user_id == user_id
                )
            )
            assert user is not None and user.email_verified is True
            assert challenge is not None and challenge.used_at is not None
    finally:
        cleanup_committed_user(user_id)
    assert database_counts() == baseline


def test_concurrent_invalid_attempts_have_no_lost_updates() -> None:
    baseline = database_counts()
    user_id, _email = create_committed_fixture()
    worker_count = 7
    barrier = Barrier(worker_count)
    provider = CaptureProvider()

    def attempt() -> str:
        barrier.wait()
        with Session(engine) as session:
            try:
                EmailVerificationService(
                    phase_settings(),
                    delivery_provider=provider,
                ).verify(session, user_id=user_id, submitted_code=WRONG_CODE)
            except EmailVerificationError:
                return "invalid"
            return "unexpected-success"

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            outcomes = list(executor.map(lambda _index: attempt(), range(worker_count)))
        assert outcomes == ["invalid"] * worker_count
        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(EmailVerificationCode).where(
                    EmailVerificationCode.user_id == user_id
                )
            )
            assert user is not None and user.email_verified is False
            assert challenge is not None and challenge.attempts == 5
    finally:
        cleanup_committed_user(user_id)
    assert database_counts() == baseline


def test_concurrent_resend_leaves_at_most_one_usable_challenge() -> None:
    baseline = database_counts()
    user_id: str | None = None
    provider = CaptureProvider()
    barrier = Barrier(2)
    try:
        with Session(engine) as setup, setup.begin():
            user = create_user(setup, label="concurrent-resend")
            user_id = user.id

        def request_code() -> str:
            barrier.wait()
            with Session(engine) as session:
                try:
                    EmailVerificationService(
                        phase_settings(),
                        delivery_provider=provider,
                    ).resend(session, user_id=user_id)
                except EmailVerificationError:
                    return "limited"
                return "sent"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: request_code(), range(2)))
        assert sorted(outcomes) == ["limited", "sent"]
        with Session(engine) as audit:
            usable = int(
                audit.scalar(
                    select(func.count())
                    .select_from(EmailVerificationCode)
                    .where(
                        EmailVerificationCode.user_id == user_id,
                        EmailVerificationCode.activated_at.is_not(None),
                        EmailVerificationCode.used_at.is_(None),
                    )
                )
                or 0
            )
            assert usable == 1
    finally:
        if user_id is not None:
            cleanup_committed_user(user_id)
    assert database_counts() == baseline


def test_verify_during_delayed_resend_cannot_resurrect_stale_challenge() -> None:
    baseline = database_counts()
    old_created = utc_now() - timedelta(minutes=2)
    user_id, _email = create_committed_fixture(created_at=old_created)
    provider = BlockingProvider()

    def delayed_resend() -> str:
        with Session(engine) as session:
            EmailVerificationService(
                phase_settings(),
                delivery_provider=provider,
                code_generator=lambda: "654321",
            ).resend(session, user_id=user_id)
        return "sent"

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(delayed_resend)
            assert provider.delivery_started.wait(timeout=10)
            with Session(engine) as verification_session:
                EmailVerificationService(
                    phase_settings(),
                    delivery_provider=CaptureProvider(),
                ).verify(
                    verification_session,
                    user_id=user_id,
                    submitted_code=VALID_CODE,
                )
            provider.release_delivery.set()
            assert future.result(timeout=10) == "sent"

        with Session(engine) as audit:
            user = audit.get(User, user_id)
            rows = list(
                audit.scalars(
                    select(EmailVerificationCode)
                    .where(EmailVerificationCode.user_id == user_id)
                    .order_by(EmailVerificationCode.created_at)
                )
            )
            assert user is not None and user.email_verified is True
            assert len(rows) == 2
            assert rows[0].used_at is not None
            assert rows[1].activated_at is None and rows[1].used_at is not None
    finally:
        provider.release_delivery.set()
        cleanup_committed_user(user_id)
    assert database_counts() == baseline
