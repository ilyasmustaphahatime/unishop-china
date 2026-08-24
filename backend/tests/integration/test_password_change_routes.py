import json
import secrets
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_access_token_service,
    get_login_identifier_rate_limiter,
    get_login_ip_rate_limiter,
    get_password_change_ip_rate_limiter,
    get_password_change_service,
    get_password_change_user_rate_limiter,
    get_refresh_ip_rate_limiter,
    get_refresh_session_rate_limiter,
)
from app.common.enums import AccountStatus, UserRoleType
from app.core.config import Settings, settings
from app.core.database import engine, get_db
from app.core.exceptions import InvalidPasswordChangeError
from app.core.exceptions import InvalidPasswordResetError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password, hash_password_reset_code, verify_password
from app.core.session_security import hash_csrf_token, hash_refresh_token
from app.main import app
from app.models import (
    PasswordResetCode,
    PhoneVerificationCode,
    RefreshToken,
    User,
    UserRole,
)
from app.models.base import utc_now
from app.repositories.password_reset_code_repository import PasswordResetCodeRepository
from app.repositories.token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.password_change_service import (
    GENERIC_INVALID_PASSWORD_CHANGE_MESSAGE,
    PASSWORD_CHANGE_SUCCESS_MESSAGE,
    PasswordChangeService,
)
from app.services.password_reset_service import PasswordResetCompletionService
from app.services.token_service import AccessTokenService

TEST_JWT_SECRET = "phase-5c-test-jwt-secret-with-more-than-thirty-two-characters"
TEST_CODE_SECRET = "phase-5c-test-code-secret-with-more-than-thirty-two-characters"
CURRENT_PASSWORD = "CurrentStrongPassword123"
NEW_PASSWORD = "NewStrongPassword456"
ALTERNATE_PASSWORD = "AlternateStrongPassword789"


def token_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
        "jwt_algorithm": "HS256",
        "access_token_expire_minutes": 15,
        "jwt_issuer": "unishop-china-api",
        "jwt_audience": "unishop-china-web",
        "jwt_clock_skew_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def unlimited_limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_requests=1000, window_seconds=900, max_keys=1000)


@pytest.fixture
def token_service() -> AccessTokenService:
    return AccessTokenService(token_settings())


@pytest.fixture
def client(
    db_session: Session,
    token_service: AccessTokenService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_token_service] = lambda: token_service
    for dependency in (
        get_login_ip_rate_limiter,
        get_login_identifier_rate_limiter,
        get_password_change_ip_rate_limiter,
        get_password_change_user_rate_limiter,
        get_refresh_ip_rate_limiter,
        get_refresh_session_rate_limiter,
    ):
        app.dependency_overrides[dependency] = unlimited_limiter
    try:
        with TestClient(
            app,
            client=("198.51.100.92", 55000),
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def unique_email(label: str) -> str:
    return f"phase5c-{label}-{uuid4().hex}@example.com"


def create_user(
    session: Session,
    *,
    label: str,
    password: str = CURRENT_PASSWORD,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=unique_email(label),
        password_hash=hash_password(password),
        account_status=status,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
    session.flush()
    return user


def create_reset_challenge(
    session: Session,
    *,
    user: User,
    code: str = "123456",
) -> PasswordResetCode:
    now = utc_now()
    challenge = PasswordResetCode(
        user_id=user.id,
        code_hash=hash_password_reset_code(code, TEST_CODE_SECRET),
        expires_at=now + timedelta(minutes=10),
        attempts=0,
    )
    session.add(challenge)
    session.flush()
    return challenge


def create_refresh_session(
    session: Session,
    *,
    user: User,
) -> tuple[RefreshToken, str, str]:
    now = utc_now()
    raw_refresh = secrets.token_urlsafe(64)
    raw_csrf = secrets.token_urlsafe(32)
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=str(uuid4()),
        csrf_token_hash=hash_csrf_token(raw_csrf),
        expires_at=now + timedelta(days=7),
        family_expires_at=now + timedelta(days=30),
    )
    session.add(refresh)
    session.flush()
    return refresh, raw_refresh, raw_csrf


def authorization(token: str, *, origin: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if origin is not None:
        headers["Origin"] = origin
    return headers


def payload(
    *,
    current_password: str = CURRENT_PASSWORD,
    new_password: str = NEW_PASSWORD,
) -> dict[str, str]:
    return {
        "current_password": current_password,
        "new_password": new_password,
    }


def install_refresh_cookies(
    client: TestClient,
    raw_refresh: str,
    raw_csrf: str,
) -> None:
    client.cookies.clear()
    client.cookies.set(
        settings.refresh_cookie_name,
        raw_refresh,
        domain="testserver.local",
        path=settings.refresh_cookie_path,
    )
    client.cookies.set(
        settings.csrf_cookie_name,
        raw_csrf,
        domain="testserver.local",
        path=settings.csrf_cookie_path,
    )


def assert_generic_change_failure(response: object) -> None:
    assert response.status_code == 400
    assert response.json() == {"detail": GENERIC_INVALID_PASSWORD_CHANGE_MESSAGE}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(contains_key(child, key) for child in value)
    return False


def test_successful_change_is_atomic_revokes_only_owner_and_requires_new_login(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, label="success")
    other = create_user(db_session, label="success-other")
    other_original_hash = other.password_hash
    owner_refresh, owner_raw, owner_csrf = create_refresh_session(
        db_session,
        user=user,
    )
    owner_refresh_two, _, _ = create_refresh_session(db_session, user=user)
    other_refresh, _, _ = create_refresh_session(db_session, user=other)
    owner_challenge = create_reset_challenge(db_session, user=user)
    other_challenge = create_reset_challenge(db_session, user=other)
    old_hash = user.password_hash

    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": CURRENT_PASSWORD},
    )
    assert login.status_code == 200
    access_token = login.json()["access_token"]

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=authorization(access_token, origin="http://localhost:5173"),
    )

    assert response.status_code == 200
    assert response.json() == {"message": PASSWORD_CHANGE_SUCCESS_MESSAGE}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert CURRENT_PASSWORD not in response.text
    assert NEW_PASSWORD not in response.text
    assert owner_raw not in response.text
    assert owner_csrf not in response.text
    cookie_headers = response.headers.get_list("set-cookie")
    assert any(settings.refresh_cookie_name in header and "Max-Age=0" in header for header in cookie_headers)
    assert any(settings.csrf_cookie_name in header and "Max-Age=0" in header for header in cookie_headers)

    db_session.expire_all()
    changed_user = db_session.get(User, user.id)
    assert changed_user is not None
    assert changed_user.password_hash != old_hash
    assert changed_user.password_hash.startswith("$argon2id$")
    assert CURRENT_PASSWORD not in changed_user.password_hash
    assert NEW_PASSWORD not in changed_user.password_hash
    assert not verify_password(CURRENT_PASSWORD, changed_user.password_hash)
    assert verify_password(NEW_PASSWORD, changed_user.password_hash)
    for refresh in (owner_refresh, owner_refresh_two):
        db_session.refresh(refresh)
        assert refresh.revoked_at is not None
        assert refresh.revocation_reason == "logout_all"
    all_preexisting_owner_refreshes = list(
        db_session.scalars(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )
    )
    assert len(all_preexisting_owner_refreshes) == 3
    assert all(row.revoked_at is not None for row in all_preexisting_owner_refreshes)
    db_session.refresh(other_refresh)
    db_session.refresh(other)
    assert other_refresh.revoked_at is None
    assert other.password_hash == other_original_hash
    db_session.refresh(owner_challenge)
    db_session.refresh(other_challenge)
    assert owner_challenge.used_at is not None
    assert other_challenge.used_at is None

    with pytest.raises(InvalidPasswordResetError):
        PasswordResetCompletionService(token_settings()).reset_password(
            db_session,
            identifier=user.email or "",
            identifier_kind="email",
            code="123456",
            new_password=ALTERNATE_PASSWORD,
        )
    db_session.refresh(changed_user)
    assert verify_password(NEW_PASSWORD, changed_user.password_hash)

    install_refresh_cookies(client, owner_raw, owner_csrf)
    old_refresh_response = client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": owner_csrf},
    )
    assert old_refresh_response.status_code == 401

    old_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": CURRENT_PASSWORD},
    )
    new_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": NEW_PASSWORD},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200

    # Access JWTs are stateless in the approved architecture and expire naturally.
    residual_access = client.get(
        "/api/v1/auth/me",
        headers=authorization(access_token),
    )
    assert residual_access.status_code == 200
    assert residual_access.json()["id"] == user.id


def test_wrong_current_password_is_generic_and_mutation_free(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="wrong-current")
    challenge = create_reset_challenge(db_session, user=user)
    refresh, _, _ = create_refresh_session(db_session, user=user)
    original_hash = user.password_hash

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(current_password="WrongCurrentPassword123"),
        headers=authorization(token_service.create_access_token(user.id)),
    )

    assert_generic_change_failure(response)
    db_session.refresh(user)
    db_session.refresh(challenge)
    db_session.refresh(refresh)
    assert user.password_hash == original_hash
    assert challenge.used_at is None
    assert refresh.revoked_at is None


def test_same_password_is_generic_and_mutation_free(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="same")
    challenge = create_reset_challenge(db_session, user=user)
    refresh, _, _ = create_refresh_session(db_session, user=user)
    original_hash = user.password_hash

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(new_password=CURRENT_PASSWORD),
        headers=authorization(token_service.create_access_token(user.id)),
    )

    assert_generic_change_failure(response)
    db_session.refresh(user)
    db_session.refresh(challenge)
    db_session.refresh(refresh)
    assert user.password_hash == original_hash
    assert challenge.used_at is None
    assert refresh.revoked_at is None


def test_bearer_authority_does_not_require_refresh_or_csrf_cookie(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="bearer-only")
    client.cookies.clear()

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=authorization(token_service.create_access_token(user.id)),
    )

    assert response.status_code == 200
    db_session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)


def test_foreign_origin_is_rejected_before_mutation(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="foreign-origin")
    original_hash = user.password_hash

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=authorization(
            token_service.create_access_token(user.id),
            origin="https://attacker.example",
        ),
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Request verification failed."}
    db_session.refresh(user)
    assert user.password_hash == original_hash


@pytest.mark.parametrize(
    "authorization_value",
    [None, "Bearer malformed", "Basic credentials"],
)
def test_unauthenticated_or_malformed_authentication_is_blocked(
    authorization_value: str | None,
    client: TestClient,
) -> None:
    headers = (
        {"Authorization": authorization_value}
        if authorization_value is not None
        else None
    )

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=headers,
    )

    assert response.status_code == 401


def test_expired_and_invalid_signature_tokens_are_blocked(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, label="invalid-token")
    now = datetime.now(timezone.utc)
    base_claims = {
        "sub": user.id,
        "type": "access",
        "jti": "phase5c-test-token",
        "iss": "unishop-china-api",
        "aud": "unishop-china-web",
        "iat": now - timedelta(hours=1),
        "nbf": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=30),
    }
    expired = jwt.encode(base_claims, TEST_JWT_SECRET, algorithm="HS256")
    invalid_signature = jwt.encode(
        {**base_claims, "exp": now + timedelta(minutes=5)},
        "different-test-secret-with-more-than-thirty-two-characters",
        algorithm="HS256",
    )

    for token in (expired, invalid_signature):
        response = client.post(
            "/api/v1/auth/password/change",
            json=payload(),
            headers=authorization(token),
        )
        assert response.status_code == 401
    db_session.refresh(user)
    assert verify_password(CURRENT_PASSWORD, user.password_hash)


def test_account_that_became_ineligible_is_blocked_without_reactivation(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="inactive")
    token = token_service.create_access_token(user.id)
    user.account_status = AccountStatus.SUSPENDED
    db_session.flush()

    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=authorization(token),
    )

    assert response.status_code == 401
    db_session.refresh(user)
    assert user.account_status is AccountStatus.SUSPENDED
    assert verify_password(CURRENT_PASSWORD, user.password_hash)


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "email",
        "phone",
        "role",
        "is_admin",
        "password_hash",
        "session_id",
        "refresh_token",
        "access_token",
        "account_status",
        "verification_status",
    ],
)
def test_idor_and_mass_assignment_fields_are_rejected(
    field: str,
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label=f"mass-{field}")
    victim = create_user(db_session, label=f"victim-{field}")
    original_user_hash = user.password_hash
    original_victim_hash = victim.password_hash
    request_payload: dict[str, object] = {
        **payload(),
        field: victim.id if field == "user_id" else "SyntheticPrivilegedMarker",
    }

    response = client.post(
        "/api/v1/auth/password/change",
        json=request_payload,
        headers=authorization(token_service.create_access_token(user.id)),
    )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "SyntheticPrivilegedMarker" not in response.text
    db_session.refresh(user)
    db_session.refresh(victim)
    assert user.password_hash == original_user_hash
    assert victim.password_hash == original_victim_hash


@pytest.mark.parametrize(
    ("request_payload", "marker"),
    [
        (
            {"current_password": "CurrentSecretMarker1" + "x" * 130, "new_password": NEW_PASSWORD},
            "CurrentSecretMarker1",
        ),
        (
            {"current_password": CURRENT_PASSWORD, "new_password": "WeakNewPasswordMarker"},
            "WeakNewPasswordMarker",
        ),
        (
            {"current_password": CURRENT_PASSWORD, "new_password": "NewSecretMarker1" + "x" * 130},
            "NewSecretMarker1",
        ),
        (
            {"current_password": {"nested": "NestedCurrentSecretMarker"}, "new_password": NEW_PASSWORD},
            "NestedCurrentSecretMarker",
        ),
        (
            {"current_password": CURRENT_PASSWORD, "new_password": ["NestedNewSecretMarker"]},
            "NestedNewSecretMarker",
        ),
        (
            {**payload(), "unexpected": {"secret": "UnexpectedSecretMarker"}},
            "UnexpectedSecretMarker",
        ),
    ],
)
def test_validation_never_reflects_password_or_nested_secret_input(
    request_payload: dict[str, object],
    marker: str,
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session, label="validation")
    original_hash = user.password_hash

    response = client.post(
        "/api/v1/auth/password/change",
        json=request_payload,
        headers=authorization(token_service.create_access_token(user.id)),
    )

    assert response.status_code == 422
    response_payload = response.json()
    serialized = json.dumps(response_payload, ensure_ascii=False)
    assert marker not in serialized
    for forbidden_key in ("input", "ctx", "url"):
        assert not contains_key(response_payload, forbidden_key)
    db_session.refresh(user)
    assert user.password_hash == original_hash


def test_user_rate_limit_is_hmac_keyed_and_mutation_free(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=900, max_keys=100)
    app.dependency_overrides[get_password_change_user_rate_limiter] = lambda: limiter
    user = create_user(db_session, label="user-limit")
    challenge = create_reset_challenge(db_session, user=user)
    refresh, _, _ = create_refresh_session(db_session, user=user)
    token = token_service.create_access_token(user.id)

    first = client.post(
        "/api/v1/auth/password/change",
        json=payload(current_password="WrongCurrentPassword123"),
        headers=authorization(token),
    )
    blocked = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=authorization(token),
    )

    assert_generic_change_failure(first)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["cache-control"] == "no-store"
    assert len(limiter._requests) == 1
    assert user.id not in next(iter(limiter._requests))
    db_session.refresh(user)
    db_session.refresh(challenge)
    db_session.refresh(refresh)
    assert verify_password(CURRENT_PASSWORD, user.password_hash)
    assert challenge.used_at is None
    assert refresh.revoked_at is None


def test_ip_rate_limit_uses_peer_and_ignores_forwarded_headers(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=900, max_keys=100)
    app.dependency_overrides[get_password_change_ip_rate_limiter] = lambda: limiter
    first_user = create_user(db_session, label="ip-limit-one")
    second_user = create_user(db_session, label="ip-limit-two")

    first = client.post(
        "/api/v1/auth/password/change",
        json=payload(current_password="WrongCurrentPassword123"),
        headers=authorization(token_service.create_access_token(first_user.id)),
    )
    blocked_headers = authorization(token_service.create_access_token(second_user.id))
    blocked_headers["X-Forwarded-For"] = "203.0.113.250"
    blocked = client.post(
        "/api/v1/auth/password/change",
        json=payload(),
        headers=blocked_headers,
    )

    assert_generic_change_failure(first)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert list(limiter._requests) == ["198.51.100.92"]
    db_session.refresh(second_user)
    assert verify_password(CURRENT_PASSWORD, second_user.password_hash)


def test_unexpected_service_error_is_safe_and_does_not_log_secrets(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingService:
        def change_password(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("SyntheticInternalDatabaseDetail")

    app.dependency_overrides[get_password_change_service] = lambda: FailingService()
    user = create_user(db_session, label="safe-error")
    current_marker = "CurrentSensitiveMarker123"
    new_marker = "NewSensitiveMarker456"

    access_token = token_service.create_access_token(user.id)
    response = client.post(
        "/api/v1/auth/password/change",
        json=payload(current_password=current_marker, new_password=new_marker),
        headers=authorization(access_token),
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "Password change could not be completed."}
    assert response.headers["cache-control"] == "no-store"
    for secret_value in (
        current_marker,
        new_marker,
        access_token,
        "SyntheticInternalDatabaseDetail",
    ):
        assert secret_value not in response.text
        assert secret_value not in caplog.text
    db_session.refresh(user)
    assert verify_password(CURRENT_PASSWORD, user.password_hash)


@pytest.mark.parametrize(
    "failure_point",
    ["password_update", "reset_invalidation", "session_revocation"],
)
def test_required_mutation_failure_rolls_back_all_security_state(
    failure_point: str,
    db_session: Session,
) -> None:
    class FailingUserRepository(UserRepository):
        def update_password_hash(self, user: User, password_hash: str) -> None:
            if failure_point == "password_update":
                raise RuntimeError("injected password update failure")
            super().update_password_hash(user, password_hash)

    class FailingResetRepository(PasswordResetCodeRepository):
        def invalidate_active_for_user(self, *args: object, **kwargs: object) -> int:
            if failure_point == "reset_invalidation":
                raise RuntimeError("injected reset invalidation failure")
            return super().invalidate_active_for_user(*args, **kwargs)

    class FailingRefreshRepository(RefreshTokenRepository):
        def revoke_all_for_user(self, *args: object, **kwargs: object) -> int:
            if failure_point == "session_revocation":
                raise RuntimeError("injected refresh revocation failure")
            return super().revoke_all_for_user(*args, **kwargs)

    user = create_user(db_session, label=f"rollback-{failure_point}")
    challenge = create_reset_challenge(db_session, user=user)
    refresh, _, _ = create_refresh_session(db_session, user=user)
    original_hash = user.password_hash
    service = PasswordChangeService(
        user_repository=FailingUserRepository(),
        reset_repository=FailingResetRepository(),
        refresh_repository=FailingRefreshRepository(),
    )

    with pytest.raises(RuntimeError):
        service.change_password(
            db_session,
            user_id=user.id,
            current_password=CURRENT_PASSWORD,
            new_password=NEW_PASSWORD,
        )

    db_session.expire_all()
    persisted_user = db_session.get(User, user.id)
    persisted_challenge = db_session.get(PasswordResetCode, challenge.id)
    persisted_refresh = db_session.get(RefreshToken, refresh.id)
    assert persisted_user is not None
    assert persisted_challenge is not None
    assert persisted_refresh is not None
    assert persisted_user.password_hash == original_hash
    assert verify_password(CURRENT_PASSWORD, persisted_user.password_hash)
    assert not verify_password(NEW_PASSWORD, persisted_user.password_hash)
    assert persisted_challenge.used_at is None
    assert persisted_refresh.revoked_at is None


def _database_snapshot() -> tuple[tuple[int, ...], frozenset[str]]:
    models = (User, UserRole, PhoneVerificationCode, RefreshToken, PasswordResetCode)
    with Session(engine) as session:
        counts = tuple(
            int(session.scalar(select(func.count()).select_from(model)) or 0)
            for model in models
        )
        user_ids = frozenset(session.scalars(select(User.id)))
    return counts, user_ids


def test_concurrent_changes_allow_exactly_one_stale_credential_transition() -> None:
    baseline = _database_snapshot()
    user_id: str | None = None
    try:
        with Session(engine) as setup:
            with setup.begin():
                user = create_user(setup, label="concurrent")
                create_reset_challenge(setup, user=user)
                create_refresh_session(setup, user=user)
                user_id = user.id

        barrier = Barrier(2)

        def attempt(new_password: str) -> tuple[str, str]:
            assert user_id is not None
            with Session(engine) as session:
                barrier.wait(timeout=10)
                try:
                    PasswordChangeService().change_password(
                        session,
                        user_id=user_id,
                        current_password=CURRENT_PASSWORD,
                        new_password=new_password,
                    )
                except InvalidPasswordChangeError:
                    return "rejected", new_password
                return "changed", new_password

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(attempt, (NEW_PASSWORD, ALTERNATE_PASSWORD))
            )

        assert [status for status, _ in results].count("changed") == 1
        assert [status for status, _ in results].count("rejected") == 1
        winner = next(password for status, password in results if status == "changed")
        loser = next(password for status, password in results if status == "rejected")

        with Session(engine) as audit:
            persisted_user = audit.get(User, user_id)
            assert persisted_user is not None
            assert verify_password(winner, persisted_user.password_hash)
            assert not verify_password(loser, persisted_user.password_hash)
            assert not verify_password(CURRENT_PASSWORD, persisted_user.password_hash)
            challenges = list(
                audit.scalars(
                    select(PasswordResetCode).where(
                        PasswordResetCode.user_id == user_id
                    )
                )
            )
            refresh_rows = list(
                audit.scalars(
                    select(RefreshToken).where(RefreshToken.user_id == user_id)
                )
            )
            assert challenges and all(row.used_at is not None for row in challenges)
            assert refresh_rows and all(row.revoked_at is not None for row in refresh_rows)
    finally:
        if user_id is not None:
            with Session(engine) as cleanup:
                with cleanup.begin():
                    cleanup.execute(delete(User).where(User.id == user_id))

    assert _database_snapshot() == baseline


def test_phase_5c_openapi_inventory_is_exact_and_future_routes_are_absent() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/auth/password/change" in paths
    assert "post" in paths["/api/v1/auth/password/change"]
    assert sum(path == "/api/v1/auth/password/change" for path in paths) == 1
    assert sum(path == "/api/v1/auth/password/forgot" for path in paths) == 1
    assert sum(path == "/api/v1/auth/password/reset" for path in paths) == 1
    assert not any("email/verify" in path for path in paths)
    assert not any("phase-5d" in path.lower() for path in paths)
