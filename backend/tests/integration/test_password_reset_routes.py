from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_login_identifier_rate_limiter,
    get_login_ip_rate_limiter,
    get_password_reset_completion_service,
    get_password_reset_identifier_rate_limiter,
    get_password_reset_ip_rate_limiter,
    get_refresh_ip_rate_limiter,
    get_refresh_session_rate_limiter,
)
from app.common.enums import AccountStatus, UserRoleType
from app.core.config import Settings, settings
from app.core.database import engine, get_db
from app.core.exceptions import InvalidPasswordResetError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import (
    hash_password,
    hash_password_reset_code,
    verify_password,
)
from app.core.session_security import hash_csrf_token, hash_refresh_token
from app.main import app
from app.models import PasswordResetCode, RefreshToken, User, UserRole
from app.repositories.password_reset_code_repository import PasswordResetCodeRepository
from app.repositories.token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.password_reset_service import (
    GENERIC_INVALID_PASSWORD_RESET_MESSAGE,
    PASSWORD_RESET_SUCCESS_MESSAGE,
    PasswordResetCompletionService,
)

TEST_JWT_SECRET = "phase-5b-test-jwt-secret-with-more-than-thirty-two-characters"
TEST_CODE_SECRET = "phase-5b-test-code-secret-with-more-than-thirty-two-characters"
OLD_PASSWORD = "OldStrongPassword123"
NEW_PASSWORD = "NewStrongPassword456"
CODE = "123456"


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def reset_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
        "password_reset_max_attempts": 5,
    }
    values.update(overrides)
    return Settings(**values)


def unlimited_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_requests=1000, window_seconds=900, max_keys=1000)


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def create_user(
    session: Session,
    *,
    email: str | None = None,
    phone: str | None = None,
    password: str = OLD_PASSWORD,
    status: AccountStatus = AccountStatus.ACTIVE,
    add_role: bool = True,
) -> User:
    user = User(
        email=email,
        phone_number=phone,
        password_hash=hash_password(password),
        account_status=status,
    )
    session.add(user)
    session.flush()
    if add_role:
        session.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
        session.flush()
    return user


def create_challenge(
    session: Session,
    *,
    user: User,
    clock: MutableClock,
    code: str = CODE,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
    attempts: int = 0,
) -> PasswordResetCode:
    record = PasswordResetCode(
        user_id=user.id,
        code_hash=hash_password_reset_code(code, TEST_CODE_SECRET),
        expires_at=expires_at or clock.now + timedelta(minutes=10),
        used_at=used_at,
        attempts=attempts,
        created_at=created_at or clock.now,
    )
    session.add(record)
    session.flush()
    return record


def create_refresh_session(
    session: Session,
    *,
    user: User,
    clock: MutableClock,
) -> tuple[RefreshToken, str, str]:
    raw_token = secrets.token_urlsafe(64)
    csrf_token = secrets.token_urlsafe(32)
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_token),
        family_id=str(uuid4()),
        csrf_token_hash=hash_csrf_token(csrf_token),
        expires_at=clock.now + timedelta(days=7),
        family_expires_at=clock.now + timedelta(days=30),
    )
    session.add(record)
    session.flush()
    return record, raw_token, csrf_token


def install_refresh_cookies(client: TestClient, raw_token: str, csrf_token: str) -> None:
    client.cookies.clear()
    client.cookies.set(
        settings.refresh_cookie_name,
        raw_token,
        domain="testserver.local",
        path=settings.refresh_cookie_path,
    )
    client.cookies.set(
        settings.csrf_cookie_name,
        csrf_token,
        domain="testserver.local",
        path=settings.csrf_cookie_path,
    )


def reset_payload(
    identifier: str,
    *,
    code: str = CODE,
    new_password: str = NEW_PASSWORD,
) -> dict[str, str]:
    return {
        "identifier": identifier,
        "code": code,
        "new_password": new_password,
    }


def assert_invalid(response) -> None:
    assert response.status_code == 400
    assert response.json() == {"detail": GENERIC_INVALID_PASSWORD_RESET_MESSAGE}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def database_counts() -> tuple[int, ...]:
    models = (User, UserRole, PasswordResetCode, RefreshToken)
    with Session(engine) as session:
        return tuple(
            int(session.scalar(select(func.count()).select_from(model)) or 0)
            for model in models
        )


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime.now(timezone.utc).replace(microsecond=0))


@pytest.fixture
def service(clock: MutableClock) -> PasswordResetCompletionService:
    return PasswordResetCompletionService(reset_settings(), now_provider=clock)


@pytest.fixture
def client(
    db_session: Session,
    service: PasswordResetCompletionService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_password_reset_completion_service] = lambda: service
    for dependency in (
        get_password_reset_ip_rate_limiter,
        get_password_reset_identifier_rate_limiter,
        get_login_ip_rate_limiter,
        get_login_identifier_rate_limiter,
        get_refresh_ip_rate_limiter,
        get_refresh_session_rate_limiter,
    ):
        app.dependency_overrides[dependency] = unlimited_limiter
    try:
        with TestClient(
            app,
            client=("198.51.100.61", 54000),
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_valid_reset_is_atomic_consumes_codes_and_revokes_only_user_sessions(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("valid-reset"))
    other = create_user(db_session, email=unique_email("unrelated"))
    older = create_challenge(
        db_session,
        user=user,
        clock=clock,
        code="111111",
        created_at=clock.now - timedelta(seconds=1),
    )
    current = create_challenge(db_session, user=user, clock=clock)
    other_challenge = create_challenge(db_session, user=other, clock=clock)
    first_refresh, raw_refresh, csrf = create_refresh_session(
        db_session, user=user, clock=clock
    )
    second_refresh, _, _ = create_refresh_session(db_session, user=user, clock=clock)
    other_refresh, _, _ = create_refresh_session(db_session, user=other, clock=clock)

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
    )

    assert response.status_code == 200
    assert response.json() == {"message": PASSWORD_RESET_SUCCESS_MESSAGE}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "set-cookie" not in response.headers
    assert {"access_token", "refresh_token", "user"}.isdisjoint(response.json())
    for record in (
        user,
        older,
        current,
        other_challenge,
        first_refresh,
        second_refresh,
        other_refresh,
    ):
        db_session.refresh(record)
    assert user.password_hash != NEW_PASSWORD
    assert user.password_hash.startswith("$argon2")
    assert verify_password(OLD_PASSWORD, user.password_hash) is False
    assert verify_password(NEW_PASSWORD, user.password_hash) is True
    assert current.used_at is not None
    assert older.used_at is not None
    assert other_challenge.used_at is None
    assert first_refresh.revoked_at is not None
    assert second_refresh.revoked_at is not None
    assert first_refresh.revocation_reason == second_refresh.revocation_reason == "logout_all"
    assert other_refresh.revoked_at is None

    replay = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
    )
    assert_invalid(replay)

    install_refresh_cookies(client, raw_refresh, csrf)
    old_refresh = client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf},
    )
    assert old_refresh.status_code == 401

    old_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": OLD_PASSWORD},
    )
    new_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": NEW_PASSWORD},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200


def test_attempts_progress_to_five_then_correct_code_is_rejected(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("attempt-budget"))
    challenge = create_challenge(db_session, user=user, clock=clock)
    refresh, _, _ = create_refresh_session(db_session, user=user, clock=clock)

    for expected in range(1, 6):
        response = client.post(
            "/api/v1/auth/password/reset",
            json=reset_payload(user.email or "", code="000000"),
        )
        assert_invalid(response)
        db_session.refresh(challenge)
        assert challenge.attempts == expected

    exhausted = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
    )
    assert_invalid(exhausted)
    db_session.refresh(user)
    db_session.refresh(challenge)
    db_session.refresh(refresh)
    assert challenge.attempts == 5
    assert challenge.used_at is None
    assert verify_password(OLD_PASSWORD, user.password_hash)
    assert refresh.revoked_at is None

    fresh = create_challenge(
        db_session,
        user=user,
        clock=clock,
        code="654321",
        created_at=clock.now + timedelta(seconds=1),
    )
    assert fresh.attempts == 0
    recovered = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or "", code="654321"),
    )
    assert recovered.status_code == 200
    db_session.refresh(fresh)
    assert fresh.attempts == 0
    assert fresh.used_at is not None


@pytest.mark.parametrize("submitted", ["13800000000", "0086 13800000000"])
def test_mainland_phone_identifier_resolves_the_same_account(
    submitted: str,
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, phone="+8613800000000")
    challenge = create_challenge(db_session, user=user, clock=clock)

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(submitted),
    )

    assert response.status_code == 200
    db_session.refresh(user)
    db_session.refresh(challenge)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert challenge.used_at is not None


def test_correct_code_before_attempt_exhaustion_succeeds(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("before-exhaustion"))
    challenge = create_challenge(db_session, user=user, clock=clock)

    for _ in range(2):
        assert_invalid(
            client.post(
                "/api/v1/auth/password/reset",
                json=reset_payload(user.email or "", code="000000"),
            )
        )
    success = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
    )

    assert success.status_code == 200
    db_session.refresh(challenge)
    assert challenge.attempts == 2
    assert challenge.used_at is not None


def test_expired_challenge_is_generic_and_has_no_security_side_effects(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("expired"))
    challenge = create_challenge(
        db_session,
        user=user,
        clock=clock,
        expires_at=clock.now - timedelta(seconds=1),
    )
    refresh, _, _ = create_refresh_session(db_session, user=user, clock=clock)

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
    )

    assert_invalid(response)
    db_session.refresh(user)
    db_session.refresh(challenge)
    db_session.refresh(refresh)
    assert challenge.attempts == 0
    assert challenge.used_at is None
    assert verify_password(OLD_PASSWORD, user.password_hash)
    assert refresh.revoked_at is None


def test_superseded_code_fails_and_newest_code_succeeds(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("superseded"))
    old = create_challenge(
        db_session,
        user=user,
        clock=clock,
        code="111111",
        created_at=clock.now - timedelta(seconds=1),
        used_at=clock.now - timedelta(seconds=1),
    )
    newest = create_challenge(db_session, user=user, clock=clock, code="222222")

    old_response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or "", code="111111"),
    )
    assert_invalid(old_response)
    db_session.refresh(newest)
    assert newest.attempts == 1

    newest_response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or "", code="222222"),
    )
    assert newest_response.status_code == 200
    db_session.refresh(old)
    db_session.refresh(newest)
    assert old.used_at is not None
    assert newest.used_at is not None


def test_unknown_account_returns_generic_failure_and_creates_nothing(
    client: TestClient,
    db_session: Session,
) -> None:
    before_users = int(db_session.scalar(select(func.count()).select_from(User)) or 0)
    before_codes = int(
        db_session.scalar(select(func.count()).select_from(PasswordResetCode)) or 0
    )

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(unique_email("unknown")),
    )

    assert_invalid(response)
    assert db_session.scalar(select(func.count()).select_from(User)) == before_users
    assert (
        db_session.scalar(select(func.count()).select_from(PasswordResetCode))
        == before_codes
    )


@pytest.mark.parametrize(
    "status_value",
    [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED],
)
def test_inactive_account_is_generic_and_never_reactivated(
    status_value: AccountStatus,
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(
        db_session,
        email=unique_email(status_value.value.lower()),
        status=status_value,
    )
    challenge = create_challenge(db_session, user=user, clock=clock)
    refresh, _, _ = create_refresh_session(db_session, user=user, clock=clock)

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
    )

    assert_invalid(response)
    db_session.refresh(user)
    db_session.refresh(challenge)
    db_session.refresh(refresh)
    assert user.account_status is status_value
    assert verify_password(OLD_PASSWORD, user.password_hash)
    assert challenge.attempts == 0
    assert challenge.used_at is None
    assert refresh.revoked_at is None


@pytest.mark.parametrize(
    "payload",
    [
        {"identifier": "person@example.com", "code": "１２３４５６", "new_password": NEW_PASSWORD},
        {"identifier": "person@example.com", "code": "12345a", "new_password": NEW_PASSWORD},
        {"identifier": "not-an-identifier", "code": CODE, "new_password": NEW_PASSWORD},
        {"identifier": "person@example.com", "code": CODE, "new_password": "weak"},
        {
            "identifier": "person@example.com",
            "code": CODE,
            "new_password": NEW_PASSWORD,
            "user_id": "forbidden",
        },
        {
            "identifier": "person@example.com",
            "code": CODE,
            "new_password": NEW_PASSWORD,
            "attempts": 0,
        },
    ],
)
def test_invalid_or_mass_assignment_payload_has_no_side_effects(
    payload: dict[str, object],
    client: TestClient,
    db_session: Session,
) -> None:
    before = int(
        db_session.scalar(select(func.count()).select_from(PasswordResetCode)) or 0
    )

    response = client.post("/api/v1/auth/password/reset", json=payload)

    assert response.status_code == 422
    assert (
        db_session.scalar(select(func.count()).select_from(PasswordResetCode)) == before
    )


def test_foreign_origin_is_rejected_without_attempt_increment(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    user = create_user(db_session, email=unique_email("origin"))
    challenge = create_challenge(db_session, user=user, clock=clock)

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    db_session.refresh(challenge)
    assert challenge.attempts == 0
    assert challenge.used_at is None


def test_ip_rate_limit_uses_actual_peer_and_cannot_mutate_blocked_request(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=900, max_keys=100)
    app.dependency_overrides[get_password_reset_ip_rate_limiter] = lambda: limiter
    user = create_user(db_session, email=unique_email("ip-limit"))
    challenge = create_challenge(db_session, user=user, clock=clock)

    first = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or "", code="000000"),
    )
    blocked = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or ""),
        headers={"X-Forwarded-For": "203.0.113.250"},
    )

    assert_invalid(first)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["cache-control"] == "no-store"
    assert list(limiter._requests) == ["198.51.100.61"]
    db_session.refresh(user)
    db_session.refresh(challenge)
    assert challenge.attempts == 1
    assert challenge.used_at is None
    assert verify_password(OLD_PASSWORD, user.password_hash)


def test_identifier_rate_limit_uses_normalized_hmac_key(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=900, max_keys=100)
    app.dependency_overrides[get_password_reset_identifier_rate_limiter] = (
        lambda: limiter
    )
    email = unique_email("identifier-limit")
    user = create_user(db_session, email=email)
    challenge = create_challenge(db_session, user=user, clock=clock)

    first = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(email.upper(), code="000000"),
    )
    blocked = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(f" {email} "),
    )

    assert_invalid(first)
    assert blocked.status_code == 429
    assert len(limiter._requests) == 1
    assert email not in next(iter(limiter._requests))
    db_session.refresh(challenge)
    assert challenge.attempts == 1
    assert challenge.used_at is None


def test_reset_limiter_is_bounded_and_recovers_after_window() -> None:
    now = [100.0]
    limiter = InMemoryRateLimiter(
        max_requests=1,
        window_seconds=900,
        max_keys=2,
        now_provider=lambda: now[0],
    )

    assert limiter.consume("first").allowed
    assert not limiter.consume("first").allowed
    limiter.consume("second")
    limiter.consume("third")
    assert len(limiter._requests) == 2
    now[0] += 901
    assert limiter.consume("first").allowed


def test_reset_flow_emits_no_sensitive_logs(
    client: TestClient,
    db_session: Session,
    clock: MutableClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user = create_user(db_session, email=unique_email("no-logs"))
    create_challenge(db_session, user=user, clock=clock)

    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(user.email or "", code="000000"),
    )

    assert_invalid(response)
    assert caplog.text == ""
    for secret_value in (user.email or "", "000000", NEW_PASSWORD):
        assert secret_value not in response.text


@pytest.mark.parametrize(
    "failure_point",
    ["password_update", "consume", "invalidation", "session_revocation"],
)
def test_required_state_change_failure_rolls_back_everything(
    failure_point: str,
    db_session: Session,
    clock: MutableClock,
) -> None:
    class FailingUserRepository(UserRepository):
        def update_password_hash(self, user: User, password_hash: str) -> None:
            if failure_point == "password_update":
                raise RuntimeError("injected password update failure")
            super().update_password_hash(user, password_hash)

    class FailingResetRepository(PasswordResetCodeRepository):
        def consume_if_available(self, *args: object, **kwargs: object) -> int:
            if failure_point == "consume":
                raise RuntimeError("injected consumption failure")
            return super().consume_if_available(*args, **kwargs)

        def invalidate_other_active_for_user(
            self, *args: object, **kwargs: object
        ) -> int:
            if failure_point == "invalidation":
                raise RuntimeError("injected invalidation failure")
            return super().invalidate_other_active_for_user(*args, **kwargs)

    class FailingRefreshRepository(RefreshTokenRepository):
        def revoke_all_for_user(self, *args: object, **kwargs: object) -> int:
            if failure_point == "session_revocation":
                raise RuntimeError("injected session revocation failure")
            return super().revoke_all_for_user(*args, **kwargs)

    user = create_user(db_session, email=unique_email(f"rollback-{failure_point}"))
    older = create_challenge(
        db_session,
        user=user,
        clock=clock,
        code="111111",
        created_at=clock.now - timedelta(seconds=1),
    )
    current = create_challenge(db_session, user=user, clock=clock)
    refresh, _, _ = create_refresh_session(db_session, user=user, clock=clock)
    reset_service = PasswordResetCompletionService(
        reset_settings(),
        user_repository=FailingUserRepository(),
        reset_repository=FailingResetRepository(),
        refresh_repository=FailingRefreshRepository(),
        now_provider=clock,
    )

    with pytest.raises(RuntimeError, match="injected"):
        reset_service.reset_password(
            db_session,
            identifier=user.email or "",
            identifier_kind="email",
            code=CODE,
            new_password=NEW_PASSWORD,
        )

    db_session.expire_all()
    stored_user = db_session.get(User, user.id)
    stored_older = db_session.get(PasswordResetCode, older.id)
    stored_current = db_session.get(PasswordResetCode, current.id)
    stored_refresh = db_session.get(RefreshToken, refresh.id)
    assert stored_user is not None and verify_password(
        OLD_PASSWORD, stored_user.password_hash
    )
    assert stored_older is not None and stored_older.used_at is None
    assert stored_current is not None and stored_current.used_at is None
    assert stored_current.attempts == 0
    assert stored_refresh is not None and stored_refresh.revoked_at is None


def test_unexpected_service_failure_is_safe_and_no_store(
    client: TestClient,
    db_session: Session,
) -> None:
    class FailingService:
        def reset_password(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("private database detail")

    app.dependency_overrides[get_password_reset_completion_service] = (
        lambda: FailingService()
    )
    response = client.post(
        "/api/v1/auth/password/reset",
        json=reset_payload(unique_email("internal-failure")),
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Password reset could not be completed."}
    assert response.headers["cache-control"] == "no-store"
    assert "private database detail" not in response.text
    assert db_session.scalar(select(func.count()).select_from(PasswordResetCode)) == 0


def _create_committed_reset_fixture() -> tuple[str, str]:
    email = unique_email("concurrent")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with Session(engine) as session, session.begin():
        user = create_user(session, email=email, add_role=False)
        session.add(
            PasswordResetCode(
                user_id=user.id,
                code_hash=hash_password_reset_code(CODE, TEST_CODE_SECRET),
                expires_at=now + timedelta(minutes=10),
                used_at=None,
                attempts=0,
                created_at=now,
            )
        )
        session.flush()
        return user.id, email


def _cleanup_committed_user(user_id: str) -> None:
    with Session(engine) as session, session.begin():
        session.execute(delete(User).where(User.id == user_id))


def test_concurrent_same_code_allows_exactly_one_success() -> None:
    baseline = database_counts()
    user_id, email = _create_committed_reset_fixture()
    barrier = Barrier(2)

    def attempt() -> str:
        barrier.wait()
        with Session(engine) as session:
            try:
                PasswordResetCompletionService(reset_settings()).reset_password(
                    session,
                    identifier=email,
                    identifier_kind="email",
                    code=CODE,
                    new_password=NEW_PASSWORD,
                )
            except InvalidPasswordResetError:
                return "invalid"
            return "success"

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: attempt(), range(2)))
        assert sorted(results) == ["invalid", "success"]
        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(PasswordResetCode).where(PasswordResetCode.user_id == user_id)
            )
            assert user is not None and verify_password(
                NEW_PASSWORD, user.password_hash
            )
            assert challenge is not None and challenge.used_at is not None
    finally:
        _cleanup_committed_user(user_id)
    assert database_counts() == baseline


def test_concurrent_wrong_attempts_have_no_lost_increment_or_budget_bypass() -> None:
    baseline = database_counts()
    user_id, email = _create_committed_reset_fixture()
    worker_count = 7
    barrier = Barrier(worker_count)

    def attempt() -> str:
        barrier.wait()
        with Session(engine) as session:
            try:
                PasswordResetCompletionService(reset_settings()).reset_password(
                    session,
                    identifier=email,
                    identifier_kind="email",
                    code="000000",
                    new_password=NEW_PASSWORD,
                )
            except InvalidPasswordResetError:
                return "invalid"
            return "unexpected-success"

    try:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(lambda _index: attempt(), range(worker_count)))
        assert results == ["invalid"] * worker_count
        with Session(engine) as audit:
            user = audit.get(User, user_id)
            challenge = audit.scalar(
                select(PasswordResetCode).where(PasswordResetCode.user_id == user_id)
            )
            assert user is not None and verify_password(
                OLD_PASSWORD, user.password_hash
            )
            assert challenge is not None and challenge.attempts == 5
            assert challenge.used_at is None
    finally:
        _cleanup_committed_user(user_id)
    assert database_counts() == baseline


def test_live_schema_contains_only_the_approved_attempt_security_change() -> None:
    inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("password_reset_codes")
    }
    checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("password_reset_codes")
    }

    assert columns["attempts"]["nullable"] is False
    assert str(columns["attempts"]["default"]).strip("'\"") == "0"
    assert "attempts" in checks["ck_password_reset_codes_attempts_non_negative"]
    assert ">= 0" in checks["ck_password_reset_codes_attempts_non_negative"]
    assert set(columns) == {
        "user_id",
        "code_hash",
        "expires_at",
        "used_at",
        "attempts",
        "id",
        "created_at",
    }


def test_openapi_preserves_phase_5a_and_5b_routes_with_phase_5c_once() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/password/forgot" in paths
    assert "post" in paths["/api/v1/auth/password/forgot"]
    assert "/api/v1/auth/password/reset" in paths
    assert "post" in paths["/api/v1/auth/password/reset"]
    assert sum(path == "/api/v1/auth/password/forgot" for path in paths) == 1
    assert sum(path == "/api/v1/auth/password/reset" for path in paths) == 1
    assert not any("email/verify" in path for path in paths)
    assert sum(path == "/api/v1/auth/password/change" for path in paths) == 1
    assert "post" in paths["/api/v1/auth/password/change"]
