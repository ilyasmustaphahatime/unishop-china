from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import (
    get_access_token_service,
    get_authentication_service,
    get_login_identifier_rate_limiter,
    get_login_ip_rate_limiter,
)
from app.common.enums import AccountStatus, UserRoleType
from app.core.config import Settings
from app.core.database import get_db
from app.core.exceptions import InvalidCredentialsError
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import hash_password
from app.main import app
from app.models import PhoneVerificationCode, RefreshToken, User, UserRole
from app.services.token_service import AccessTokenService

TEST_JWT_SECRET = "phase-4a-integration-jwt-secret-with-more-than-thirty-two-characters"
PASSWORD = "StrongPassword123"
FORBIDDEN_FIELDS = {
    "password",
    "password_hash",
    "otp",
    "code",
    "code_hash",
    "refresh_token",
    "refresh_tokens",
    "verification_codes",
    "jwt_secret",
}


class MutableClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


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

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_access_token_service] = lambda: token_service
    app.dependency_overrides[get_login_ip_rate_limiter] = lambda: InMemoryRateLimiter(
        max_requests=1000, window_seconds=60, max_keys=1000
    )
    app.dependency_overrides[get_login_identifier_rate_limiter] = (
        lambda: InMemoryRateLimiter(max_requests=1000, window_seconds=900, max_keys=1000)
    )
    try:
        with TestClient(
            app,
            client=("198.51.100.10", 50000),
            raise_server_exceptions=False,
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_user(
    session: Session,
    *,
    email: str | None = None,
    phone: str | None = None,
    password: str = PASSWORD,
    account_status: AccountStatus = AccountStatus.ACTIVE,
    email_verified: bool = False,
    phone_verified: bool = False,
    roles: tuple[UserRoleType, ...] = (UserRoleType.BUYER,),
) -> User:
    user = User(
        email=email,
        phone_number=phone,
        password_hash=hash_password(password),
        account_status=account_status,
        email_verified=email_verified,
        phone_verified=phone_verified,
    )
    session.add(user)
    session.flush()
    for role in roles:
        session.add(UserRole(user_id=user.id, role=role))
    session.flush()
    return user


def unique_email(label: str) -> str:
    return f"{label}.{uuid4().hex}@example.com"


def unique_phone() -> str:
    return f"+86138{uuid4().int % 100_000_000:08d}"


def assert_safe_user(payload: dict[str, object]) -> None:
    assert FORBIDDEN_FIELDS.isdisjoint(payload)
    assert set(payload) == {
        "id",
        "email",
        "phone_number",
        "email_verified",
        "phone_verified",
        "account_status",
        "roles",
        "created_at",
    }


@pytest.mark.parametrize("login_kind", ["email", "phone", "both-email", "both-phone"])
def test_successful_login_by_email_or_phone(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
    login_kind: str,
) -> None:
    email = unique_email(login_kind)
    phone = unique_phone()
    user = create_user(
        db_session,
        email=email if "email" in login_kind else None,
        phone=phone if "phone" in login_kind else None,
        email_verified=False,
        phone_verified=False,
    )
    if login_kind.startswith("both"):
        user.email = email
        user.phone_number = phone
        db_session.flush()
    identifier = f"  {email.upper()} " if login_kind.endswith("email") else phone

    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": PASSWORD},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == 900
    assert token_service.decode_access_token(payload["access_token"]).subject == user.id
    assert payload["user"]["id"] == user.id
    assert payload["user"]["roles"] == ["BUYER"]
    assert payload["user"]["email_verified"] is False
    assert payload["user"]["phone_verified"] is False
    assert_safe_user(payload["user"])


@pytest.mark.parametrize("identifier", ["13800000000", "0086 13800000000"])
def test_phone_login_accepts_registration_formats(
    client: TestClient,
    db_session: Session,
    identifier: str,
) -> None:
    create_user(db_session, phone="+8613800000000")
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": PASSWORD},
    )
    assert response.status_code == 200


def test_unknown_user_and_wrong_password_have_identical_public_response(
    client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("known")
    create_user(db_session, email=email)
    wrong = client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": "WrongPassword123"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("unknown"), "password": "WrongPassword123"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid credentials."}
    assert wrong.headers["www-authenticate"] == unknown.headers["www-authenticate"] == "Bearer"
    assert PASSWORD not in wrong.text


def test_unknown_phone_receives_same_generic_failure(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": "+8613900000000", "password": "WrongPassword123"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials."}


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED],
)
def test_inactive_status_is_not_revealed(
    client: TestClient,
    db_session: Session,
    account_status: AccountStatus,
) -> None:
    email = unique_email(account_status.value.lower())
    create_user(db_session, email=email, account_status=account_status)
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": PASSWORD},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials."}
    assert account_status.value not in response.text


@pytest.mark.parametrize("field", ["role", "roles", "is_admin", "account_status", "access_token"])
def test_login_rejects_privileged_extra_fields(client: TestClient, field: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("extra"), "password": PASSWORD, field: "ADMIN"},
    )
    assert response.status_code == 422


def test_valid_token_accesses_me_and_roles_are_loaded_from_database(
    client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("me")
    user = create_user(db_session, email=email, email_verified=True)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": PASSWORD},
    ).json()
    db_session.add(UserRole(user_id=user.id, role=UserRoleType.SELLER))
    db_session.flush()

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login['access_token']}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == user.id
    assert payload["email_verified"] is True
    assert payload["roles"] == ["BUYER", "SELLER"]
    assert_safe_user(payload)


@pytest.mark.parametrize(
    ("headers", "expected_status"),
    [({}, 401), ({"Authorization": "Basic synthetic"}, 401), ({"Authorization": "Bearer"}, 401)],
)
def test_me_rejects_missing_or_invalid_bearer_format(
    client: TestClient,
    headers: dict[str, str],
    expected_status: int,
) -> None:
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == expected_status
    assert response.json() == {"detail": "Could not validate credentials."}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("variant", ["expired", "issuer", "audience", "type", "missing-sub"])
def test_me_rejects_invalid_token_claims(client: TestClient, variant: str) -> None:
    now = datetime.now(timezone.utc)
    claims: dict[str, object] = {
        "sub": str(uuid4()),
        "type": "access",
        "jti": "synthetic-integration-jti",
        "iss": "unishop-china-api",
        "aud": "unishop-china-web",
        "iat": now - timedelta(minutes=1),
        "nbf": now - timedelta(minutes=1),
        "exp": now + timedelta(minutes=15),
    }
    if variant == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif variant == "issuer":
        claims["iss"] = "wrong-issuer"
    elif variant == "audience":
        claims["aud"] = "wrong-audience"
    elif variant == "type":
        claims["type"] = "refresh"
    else:
        claims.pop("sub")
    token = jwt.encode(claims, TEST_JWT_SECRET, algorithm="HS256")
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_rejects_modified_token(client: TestClient, token_service: AccessTokenService) -> None:
    token = token_service.create_access_token(str(uuid4()))
    header, payload, signature = token.split(".")
    modified = ".".join((header, payload, ("A" if signature[0] != "A" else "B") + signature[1:]))
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {modified}"},
    )
    assert response.status_code == 401


def test_me_rejects_deleted_or_inactive_user(
    client: TestClient,
    db_session: Session,
    token_service: AccessTokenService,
) -> None:
    missing_token = token_service.create_access_token(str(uuid4()))
    missing = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {missing_token}"}
    )
    assert missing.status_code == 401

    user = create_user(db_session, email=unique_email("inactive-me"))
    inactive_token = token_service.create_access_token(user.id)
    user.account_status = AccountStatus.SUSPENDED
    db_session.flush()
    inactive = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {inactive_token}"}
    )
    assert inactive.status_code == 401


def test_ip_rate_limit_uses_connection_peer_and_ignores_forwarded_header(
    client: TestClient,
    db_session: Session,
) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_login_ip_rate_limiter] = lambda: limiter
    baseline = int(db_session.scalar(select(func.count()).select_from(User)) or 0)
    first = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("ip-first"), "password": "wrong"},
    )
    blocked = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("ip-second"), "password": "wrong"},
        headers={"X-Forwarded-For": "203.0.113.200"},
    )
    assert first.status_code == 401
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert "ip-second" not in blocked.text
    assert db_session.scalar(select(func.count()).select_from(User)) == baseline


def test_rate_limited_request_does_not_invoke_authentication_service(
    client: TestClient,
) -> None:
    class CountingService:
        def __init__(self) -> None:
            self.calls = 0

        def authenticate_user_and_create_access_token(
            self, _session: Session, _request: object
        ) -> None:
            self.calls += 1
            raise InvalidCredentialsError

    service = CountingService()
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_authentication_service] = lambda: service
    app.dependency_overrides[get_login_ip_rate_limiter] = lambda: limiter

    first = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("service-first"), "password": "wrong"},
    )
    blocked = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("service-blocked"), "password": "wrong"},
    )
    assert first.status_code == 401
    assert blocked.status_code == 429
    assert service.calls == 1


def test_login_ip_limiter_keeps_connection_peers_isolated(client: TestClient) -> None:
    limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=100)
    app.dependency_overrides[get_login_ip_rate_limiter] = lambda: limiter
    first = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("peer-one"), "password": "wrong"},
    )
    blocked = client.post(
        "/api/v1/auth/login",
        json={"identifier": unique_email("peer-one-blocked"), "password": "wrong"},
    )
    with TestClient(
        app,
        client=("203.0.113.20", 50001),
        raise_server_exceptions=False,
    ) as second_client:
        isolated = second_client.post(
            "/api/v1/auth/login",
            json={"identifier": unique_email("peer-two"), "password": "wrong"},
        )
    assert first.status_code == 401
    assert blocked.status_code == 429
    assert isolated.status_code == 401


def test_identifier_rate_limit_isolated_and_recovers_with_injected_clock(
    client: TestClient,
) -> None:
    clock = MutableClock()
    limiter = InMemoryRateLimiter(
        max_requests=1,
        window_seconds=900,
        max_keys=100,
        now_provider=clock,
    )
    app.dependency_overrides[get_login_identifier_rate_limiter] = lambda: limiter
    first_identifier = unique_email("identifier-first")
    second_identifier = unique_email("identifier-second")

    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": first_identifier, "password": "wrong"},
    ).status_code == 401
    blocked = client.post(
        "/api/v1/auth/login",
        json={"identifier": first_identifier.upper(), "password": "wrong"},
    )
    assert blocked.status_code == 429
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": second_identifier, "password": "wrong"},
    ).status_code == 401

    clock.advance(900)
    recovered = client.post(
        "/api/v1/auth/login",
        json={"identifier": first_identifier, "password": "wrong"},
    )
    assert recovered.status_code == 401


def test_login_creates_no_refresh_or_verification_records(
    client: TestClient,
    db_session: Session,
) -> None:
    email = unique_email("readonly")
    create_user(db_session, email=email)
    refresh_before = int(db_session.scalar(select(func.count()).select_from(RefreshToken)) or 0)
    codes_before = int(
        db_session.scalar(select(func.count()).select_from(PhoneVerificationCode)) or 0
    )
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": email, "password": PASSWORD},
    ).status_code == 200
    assert db_session.scalar(select(func.count()).select_from(RefreshToken)) == refresh_before
    assert db_session.scalar(select(func.count()).select_from(PhoneVerificationCode)) == codes_before


def test_openapi_contains_exact_phase_4a_paths(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/auth/refresh" not in paths
    assert "/api/v1/auth/logout" not in paths
    assert "/api/v1/api/v1/auth/login" not in paths
    assert "/api/v1/auth/auth/login" not in paths
    assert "/auth/login" not in paths
