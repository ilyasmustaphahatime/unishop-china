from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_access_token_service,
    get_login_identifier_rate_limiter,
    get_login_ip_rate_limiter,
    get_logout_all_user_rate_limiter,
    get_logout_ip_rate_limiter,
    get_refresh_ip_rate_limiter,
    get_refresh_session_rate_limiter,
    get_refresh_session_service,
)
from app.common.enums import AccountStatus, UserRoleType
from app.core.config import Settings, settings
from app.core.database import engine, get_db
from app.core.exceptions import SessionRefreshError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password
from app.core.session_security import hash_csrf_token, hash_refresh_token
from app.main import app
from app.models import RefreshToken, User, UserRole
from app.models.base import utc_now
from app.repositories.token_repository import RefreshTokenRepository
from app.services.refresh_session_service import RefreshSessionService
from app.services.token_service import AccessTokenService

TEST_JWT_SECRET = "phase-4b-integration-jwt-secret-with-more-than-thirty-two-characters"
PASSWORD = "StrongPassword123"


def token_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "jwt_secret_key": TEST_JWT_SECRET,
        "jwt_algorithm": "HS256",
        "access_token_expire_minutes": 15,
        "jwt_issuer": "unishop-china-api",
        "jwt_audience": "unishop-china-web",
        "jwt_clock_skew_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def unlimited() -> InMemoryRateLimiter:
    return InMemoryRateLimiter(max_requests=1000, window_seconds=60, max_keys=1000)


@pytest.fixture
def token_service() -> AccessTokenService:
    return AccessTokenService(token_settings())


@pytest.fixture
def session_client(
    db_session: Session,
    token_service: AccessTokenService,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_token_service] = lambda: token_service
    for dependency in (
        get_login_identifier_rate_limiter,
        get_login_ip_rate_limiter,
        get_refresh_ip_rate_limiter,
        get_refresh_session_rate_limiter,
        get_logout_ip_rate_limiter,
        get_logout_all_user_rate_limiter,
    ):
        app.dependency_overrides[dependency] = unlimited
    try:
        with TestClient(
            app,
            client=("198.51.100.42", 50000),
            raise_server_exceptions=False,
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def create_user(
    session: Session,
    *,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=f"phase4b.{uuid4().hex}@example.com",
        password_hash=hash_password(PASSWORD),
        account_status=status,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=UserRoleType.BUYER))
    session.flush()
    return user


def login(client: TestClient, user: User, *, origin: str | None = None):
    headers = {"Origin": origin} if origin else None
    return client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": PASSWORD},
        headers=headers,
    )


def current_cookie_pair(client: TestClient) -> tuple[str, str]:
    return (
        client.cookies.get(
            settings.refresh_cookie_name,
            domain="testserver.local",
            path=settings.refresh_cookie_path,
        ),
        client.cookies.get(
            settings.csrf_cookie_name,
            domain="testserver.local",
            path=settings.refresh_cookie_path,
        ),
    )


def install_cookie_pair(client: TestClient, refresh: str, csrf: str) -> None:
    client.cookies.clear()
    client.cookies.set(
        settings.refresh_cookie_name,
        refresh,
        domain="testserver.local",
        path=settings.refresh_cookie_path,
    )
    client.cookies.set(
        settings.csrf_cookie_name,
        csrf,
        domain="testserver.local",
        path=settings.refresh_cookie_path,
    )


def refresh(client: TestClient, csrf: str, *, origin: str | None = None):
    headers = {"X-CSRF-Token": csrf}
    if origin:
        headers["Origin"] = origin
    return client.post("/api/v1/auth/refresh", headers=headers)


def test_login_sets_scoped_cookies_and_persists_only_hashes(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    response = login(session_client, user, origin="http://localhost:5173")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "refresh_token" not in response.json()
    raw_refresh, raw_csrf = current_cookie_pair(session_client)
    assert raw_refresh and raw_csrf
    cookie_headers = response.headers.get_list("set-cookie")
    refresh_header = next(h for h in cookie_headers if settings.refresh_cookie_name in h)
    csrf_header = next(h for h in cookie_headers if settings.csrf_cookie_name in h)
    assert "HttpOnly" in refresh_header
    assert "HttpOnly" not in csrf_header
    assert "Path=/api/v1/auth" in refresh_header
    assert "SameSite=lax" in refresh_header
    assert "Domain=" not in refresh_header

    rows = list(db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))
    assert len(rows) == 1
    row = rows[0]
    assert row.token_hash == hash_refresh_token(raw_refresh)
    assert row.csrf_token_hash == hash_csrf_token(raw_csrf)
    assert raw_refresh not in {row.token_hash, row.csrf_token_hash}
    assert raw_csrf not in {row.token_hash, row.csrf_token_hash}
    assert row.expires_at <= row.family_expires_at


def test_failed_login_and_foreign_origin_create_no_session(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    baseline = db_session.scalar(select(func.count()).select_from(RefreshToken))
    failed = session_client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": "WrongPassword123"},
    )
    foreign = login(session_client, user, origin="https://foreign.example")

    assert failed.status_code == 401
    assert foreign.status_code == 403
    assert failed.headers["cache-control"] == foreign.headers["cache-control"] == "no-store"
    assert not failed.headers.get_list("set-cookie")
    assert not foreign.headers.get_list("set-cookie")
    assert db_session.scalar(select(func.count()).select_from(RefreshToken)) == baseline


def test_login_and_refresh_validation_errors_are_not_cacheable(
    session_client: TestClient,
) -> None:
    login_error = session_client.post("/api/v1/auth/login", json={})
    refresh_error = session_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "must-not-be-accepted"},
    )

    assert login_error.status_code == 422
    assert refresh_error.status_code == 401
    for response in (login_error, refresh_error):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"


@pytest.mark.parametrize("failure", ["missing-header", "missing-cookie", "mismatch", "foreign"])
def test_refresh_csrf_and_origin_failures_do_not_rotate(
    session_client: TestClient,
    db_session: Session,
    failure: str,
) -> None:
    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    raw_refresh, raw_csrf = current_cookie_pair(session_client)
    headers: dict[str, str] = {}
    if failure != "missing-header":
        headers["X-CSRF-Token"] = "wrong" if failure == "mismatch" else raw_csrf
    if failure == "foreign":
        headers["Origin"] = "https://foreign.example"
    if failure == "missing-cookie":
        session_client.cookies.clear()
        session_client.cookies.set(
            settings.refresh_cookie_name,
            raw_refresh,
            domain="testserver.local",
            path=settings.refresh_cookie_path,
        )

    response = session_client.post("/api/v1/auth/refresh", headers=headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Request verification failed."}
    row = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
    )
    assert row is not None and row.revoked_at is None
    assert db_session.scalar(
        select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user.id)
    ) == 1


def test_missing_and_unknown_refresh_are_generic_and_clear_cookies(
    session_client: TestClient,
) -> None:
    missing = session_client.post("/api/v1/auth/refresh")
    install_cookie_pair(session_client, "unknown-refresh", "synthetic-csrf")
    unknown = refresh(session_client, "synthetic-csrf")

    for response in (missing, unknown):
        assert response.status_code == 401
        assert response.json() == {"detail": "Could not refresh session."}
        assert response.headers["cache-control"] == "no-store"
        assert len(response.headers.get_list("set-cookie")) == 2


def test_rotation_reuse_revokes_only_compromised_family(
    session_client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    family_a_old = current_cookie_pair(session_client)
    assert login(session_client, user).status_code == 200
    family_b = current_cookie_pair(session_client)

    install_cookie_pair(session_client, *family_a_old)
    rotated = refresh(session_client, family_a_old[1])
    assert rotated.status_code == 200
    assert token_service.decode_access_token(rotated.json()["access_token"]).subject == user.id
    family_a_new = current_cookie_pair(session_client)
    assert family_a_new != family_a_old
    old_row = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(family_a_old[0])
        )
    )
    new_row = db_session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(family_a_new[0])
        )
    )
    assert old_row is not None and new_row is not None
    assert old_row.revocation_reason == "rotated"
    assert old_row.replaced_by_token_id == new_row.id
    assert old_row.family_id == new_row.family_id
    assert old_row.family_expires_at == new_row.family_expires_at

    install_cookie_pair(session_client, *family_a_old)
    reused = refresh(session_client, family_a_old[1])
    assert reused.status_code == 401
    db_session.expire_all()
    family_a_rows = list(
        db_session.scalars(select(RefreshToken).where(RefreshToken.family_id == old_row.family_id))
    )
    assert family_a_rows and all(row.revocation_reason == "reuse_detected" for row in family_a_rows)

    install_cookie_pair(session_client, *family_a_new)
    assert refresh(session_client, family_a_new[1]).status_code == 401
    install_cookie_pair(session_client, *family_b)
    assert refresh(session_client, family_b[1]).status_code == 200


@pytest.mark.parametrize("expired_field", ["expires_at", "family_expires_at"])
def test_expired_or_absolute_expired_family_cannot_refresh(
    session_client: TestClient,
    db_session: Session,
    expired_field: str,
) -> None:
    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    raw_refresh, raw_csrf = current_cookie_pair(session_client)
    row = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
    )
    assert row is not None
    setattr(row, expired_field, utc_now() - timedelta(seconds=1))
    db_session.flush()

    response = refresh(session_client, raw_csrf)

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not refresh session."}
    db_session.refresh(row)
    assert row.revocation_reason == "expired_cleanup"


def test_inactive_account_refresh_revokes_family_with_generic_error(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    raw_refresh, raw_csrf = current_cookie_pair(session_client)
    user.account_status = AccountStatus.SUSPENDED
    db_session.flush()

    response = refresh(session_client, raw_csrf)

    assert response.status_code == 401
    assert "SUSPENDED" not in response.text
    row = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(raw_refresh))
    )
    assert row is not None and row.revocation_reason == "inactive_account"


def test_logout_is_csrf_protected_idempotent_and_family_scoped(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    family_a = current_cookie_pair(session_client)
    assert login(session_client, user).status_code == 200
    family_b = current_cookie_pair(session_client)

    install_cookie_pair(session_client, *family_a)
    rejected = session_client.post("/api/v1/auth/logout")
    assert rejected.status_code == 403
    logged_out = session_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": family_a[1]}
    )
    assert logged_out.status_code == 204
    assert logged_out.content == b""
    assert len(logged_out.headers.get_list("set-cookie")) == 2

    family_a_row = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(family_a[0]))
    )
    family_b_row = db_session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(family_b[0]))
    )
    assert family_a_row is not None and family_a_row.revocation_reason == "logout"
    assert family_b_row is not None and family_b_row.revoked_at is None
    assert session_client.post("/api/v1/auth/logout").status_code == 204
    install_cookie_pair(session_client, "unknown", "csrf")
    assert session_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": "csrf"}
    ).status_code == 204


def test_logout_all_requires_access_token_and_is_user_scoped(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    other = create_user(db_session)
    first_login = login(session_client, user)
    user_access = first_login.json()["access_token"]
    assert login(session_client, user).status_code == 200
    assert login(session_client, other).status_code == 200
    other_pair = current_cookie_pair(session_client)

    assert session_client.post("/api/v1/auth/logout-all").status_code == 401
    response = session_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {user_access}"},
    )
    assert response.status_code == 204
    user_rows = list(db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))
    other_rows = list(
        db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == other.id))
    )
    assert user_rows and all(row.revocation_reason == "logout_all" for row in user_rows)
    assert other_rows and all(row.revoked_at is None for row in other_rows)
    install_cookie_pair(session_client, *other_pair)
    assert refresh(session_client, other_pair[1]).status_code == 200


def test_session_family_limit_revokes_oldest_family(db_session: Session) -> None:
    user = create_user(db_session)
    config = token_settings(max_active_session_families_per_user=2)
    service = RefreshSessionService(config, access_token_service=AccessTokenService(config))
    materials = []
    for _ in range(3):
        with db_session.begin_nested():
            materials.append(service.create_login_session(db_session, user_id=user.id))

    rows = list(
        db_session.scalars(
            select(RefreshToken)
            .where(RefreshToken.user_id == user.id)
            .order_by(RefreshToken.created_at, RefreshToken.id)
        )
    )
    assert len(rows) == 3
    assert sum(row.revocation_reason == "session_limit" for row in rows) == 1
    assert sum(row.revoked_at is None for row in rows) == 2
    assert len({row.family_id for row in rows}) == 3
    assert len(materials) == 3


def test_refresh_transaction_failure_rolls_back_and_sets_no_cookie(
    session_client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    class FailingRepository(RefreshTokenRepository):
        def mark_token_rotated(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("synthetic transaction failure")

    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    original = current_cookie_pair(session_client)
    failing_service = RefreshSessionService(
        settings,
        repository=FailingRepository(),
        access_token_service=token_service,
    )
    app.dependency_overrides[get_refresh_session_service] = lambda: failing_service

    response = refresh(session_client, original[1])

    assert response.status_code == 500
    assert not response.headers.get_list("set-cookie")
    rows = list(db_session.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)))
    assert len(rows) == 1
    assert rows[0].revoked_at is None and rows[0].replaced_by_token_id is None


def test_refresh_rate_limits_use_peer_and_hashed_session_key(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    assert login(session_client, user).status_code == 200
    _raw_refresh, raw_csrf = current_cookie_pair(session_client)
    limiter = InMemoryRateLimiter(max_requests=0 + 1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_refresh_ip_rate_limiter] = lambda: limiter
    first = refresh(session_client, raw_csrf)
    new_pair = current_cookie_pair(session_client)
    blocked = refresh(session_client, new_pair[1], origin=None)

    assert first.status_code == 200
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.headers["cache-control"] == "no-store"


def test_refresh_session_limiter_hmacs_raw_token_key(session_client: TestClient) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_refresh_session_rate_limiter] = lambda: limiter
    raw_refresh = "synthetic-unknown-refresh-for-rate-limit"
    raw_csrf = "synthetic-csrf-for-rate-limit"
    install_cookie_pair(session_client, raw_refresh, raw_csrf)

    first = refresh(session_client, raw_csrf)
    install_cookie_pair(session_client, raw_refresh, raw_csrf)
    blocked = refresh(session_client, raw_csrf)

    assert first.status_code == 401
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert all(raw_refresh not in key for key in limiter._requests)


def test_logout_ip_limit_uses_peer_not_forwarded_header(session_client: TestClient) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_logout_ip_rate_limiter] = lambda: limiter

    first = session_client.post(
        "/api/v1/auth/logout", headers={"X-Forwarded-For": "203.0.113.200"}
    )
    blocked = session_client.post(
        "/api/v1/auth/logout", headers={"X-Forwarded-For": "127.0.0.1"}
    )

    assert first.status_code == 204
    assert blocked.status_code == 429
    assert "198.51.100.42" in limiter._requests
    assert "127.0.0.1" not in limiter._requests


def test_logout_all_rate_limit_is_bound_to_authenticated_user(
    session_client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    access_token = login(session_client, user).json()["access_token"]
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_logout_all_user_rate_limiter] = lambda: limiter
    headers = {"Authorization": f"Bearer {access_token}"}

    assert session_client.post("/api/v1/auth/logout-all", headers=headers).status_code == 204
    blocked = session_client.post("/api/v1/auth/logout-all", headers=headers)

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert set(limiter._requests) == {f"logout-all:user:{user.id}"}


def test_concurrent_refresh_allows_one_rotation_then_revokes_family() -> None:
    user_id: str | None = None
    family_id: str | None = None
    try:
        with Session(engine) as setup:
            with setup.begin():
                user = create_user(setup)
                user_id = user.id
            service = RefreshSessionService(settings)
            with setup.begin():
                material = service.create_login_session(setup, user_id=user_id)
                family_id = setup.scalar(
                    select(RefreshToken.family_id).where(RefreshToken.user_id == user_id)
                )

        barrier = Barrier(2)

        def rotate_once() -> str:
            with Session(engine) as worker_session:
                barrier.wait()
                try:
                    RefreshSessionService(settings).rotate_session(
                        worker_session,
                        raw_refresh_token=material.refresh_token,
                        csrf_cookie=material.csrf_token,
                        csrf_header=material.csrf_token,
                    )
                except SessionRefreshError:
                    return "rejected"
                return "rotated"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _index: rotate_once(), range(2)))

        assert sorted(outcomes) == ["rejected", "rotated"]
        with Session(engine) as audit:
            rows = list(
                audit.scalars(select(RefreshToken).where(RefreshToken.family_id == family_id))
            )
            assert len(rows) == 2
            assert sum(row.replaced_by_token_id is not None for row in rows) == 1
            ids = {row.id for row in rows}
            assert all(
                row.replaced_by_token_id is None or row.replaced_by_token_id in ids
                for row in rows
            )
            assert all(row.revocation_reason == "reuse_detected" for row in rows)
    finally:
        if user_id is not None:
            with Session(engine) as cleanup:
                with cleanup.begin():
                    cleanup.execute(delete(User).where(User.id == user_id))


def test_logout_all_commits_after_authentication_read_transaction() -> None:
    user_id: str | None = None
    try:
        with Session(engine) as setup:
            with setup.begin():
                user = create_user(setup)
                user_id = user.id
            with setup.begin():
                RefreshSessionService(settings).create_login_session(setup, user_id=user_id)

        with Session(engine) as request_session:
            assert request_session.get(User, user_id) is not None
            assert request_session.in_transaction()
            RefreshSessionService(settings).logout_all(request_session, user_id=user_id)

        with Session(engine) as audit:
            rows = list(
                audit.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id))
            )
            assert rows and all(row.revocation_reason == "logout_all" for row in rows)
    finally:
        if user_id is not None:
            with Session(engine) as cleanup:
                with cleanup.begin():
                    cleanup.execute(delete(User).where(User.id == user_id))
