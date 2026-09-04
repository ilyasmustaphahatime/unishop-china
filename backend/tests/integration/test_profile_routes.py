from collections.abc import Generator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.v1.auth.dependencies import get_current_user
from app.api.v1.profiles.dependencies import (
    get_profile_service,
    onboarding_ip_limiter,
    onboarding_user_limiter,
    profile_write_ip_limiter,
    profile_write_user_limiter,
    public_profile_ip_limiter,
)
from app.common.enums import AccountStatus, UserRoleType
from app.core.config import settings
from app.core.database import engine
from app.main import create_app
from app.models import User, UserProfile
from app.services.auth_service import SafeAuthenticatedUser


@pytest.fixture(autouse=True)
def clear_profile_rate_limiters() -> Generator[None, None, None]:
    limiters = (
        onboarding_ip_limiter,
        onboarding_user_limiter,
        profile_write_ip_limiter,
        profile_write_user_limiter,
        public_profile_ip_limiter,
    )
    for limiter in limiters:
        limiter.clear()
    yield
    for limiter in limiters:
        limiter.clear()


@pytest.fixture
def active_user() -> Generator[SafeAuthenticatedUser, None, None]:
    user_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        session.add(
            User(
                id=user_id,
                email=f"phase6-route-{user_id}@example.test",
                password_hash="not-used",
                created_at=created_at,
                updated_at=created_at,
            )
        )
    try:
        yield SafeAuthenticatedUser(
            id=user_id,
            email=f"phase6-route-{user_id}@example.test",
            phone_number=None,
            email_verified=True,
            phone_verified=False,
            account_status=AccountStatus.ACTIVE,
            roles=[UserRoleType.BUYER],
            created_at=created_at,
        )
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.id == user_id))


@pytest.fixture
def client(active_user: SafeAuthenticatedUser) -> Generator[TestClient, None, None]:
    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: active_user
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_own_profile_is_lazily_created_and_private(client: TestClient) -> None:
    response = client.get("/api/v1/profile/me")

    assert response.status_code == 200
    body = response.json()
    assert body["onboarding_completed"] is False
    assert body["display_name"] is None
    assert body["city"] is None
    assert set(body).isdisjoint(
        {"id", "user_id", "email", "phone_number", "password_hash", "roles"}
    )


def test_own_profile_requires_authentication() -> None:
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/profile/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_update_and_idempotent_server_authoritative_onboarding(client: TestClient) -> None:
    incomplete = client.post("/api/v1/profile/onboarding/complete", json={})
    assert incomplete.status_code == 409

    updated = client.patch(
        "/api/v1/profile/me",
        json={
            "display_name": "  \u5f20 \u4f1f  ",
            "bio": "  Student in Qingdao  ",
            "city": "Qingdao",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "\u5f20 \u4f1f"
    assert updated.json()["onboarding_completed"] is False

    first = client.post("/api/v1/profile/onboarding/complete", json={})
    second = client.post("/api/v1/profile/onboarding/complete", json={})
    assert first.status_code == second.status_code == 200
    assert first.json()["onboarding_completed"] is True
    assert second.json()["public_id"] == first.json()["public_id"]

    invalidated = client.patch("/api/v1/profile/me", json={"display_name": None})
    assert invalidated.status_code == 200
    assert invalidated.json()["onboarding_completed"] is False


@pytest.mark.parametrize(
    "field",
    [
        "user_id",
        "public_id",
        "role",
        "roles",
        "admin",
        "is_admin",
        "status",
        "account_status",
        "seller_verified",
        "email_verified",
        "phone_verified",
        "password",
        "password_hash",
        "onboarding_completed",
        "created_at",
        "updated_at",
    ],
)
def test_profile_update_rejects_mass_assignment(client: TestClient, field: str) -> None:
    response = client.patch(
        "/api/v1/profile/me",
        json={"display_name": "Safe Name", field: "attacker-controlled"},
    )

    assert response.status_code == 422
    serialized = response.text
    assert "attacker-controlled" not in serialized
    assert "errors.pydantic.dev" not in serialized


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": " "},
        {"display_name": "x"},
        {"display_name": "x" * 51},
        {"bio": "x" * 301},
        {"city": "Wuhan"},
        {"display_name": "safe\u0000name"},
    ],
)
def test_profile_update_rejects_invalid_values_without_reflection(
    client: TestClient,
    payload: dict[str, str],
) -> None:
    response = client.patch("/api/v1/profile/me", json=payload)

    assert response.status_code == 422
    assert "errors.pydantic.dev" not in response.text
    assert all("input" not in error and "ctx" not in error for error in response.json()["detail"])


def test_onboarding_body_is_strict(client: TestClient) -> None:
    response = client.post(
        "/api/v1/profile/onboarding/complete",
        json={"onboarding_completed": True},
    )

    assert response.status_code == 422


def test_xss_payload_remains_inert_plain_text_in_api(client: TestClient) -> None:
    payload = {
        "display_name": "<script>alert(1)</script>",
        "bio": "<img src=x onerror=alert(1)>",
        "city": "Shanghai",
    }
    response = client.patch("/api/v1/profile/me", json=payload)

    assert response.status_code == 200
    assert response.json()["display_name"] == payload["display_name"]
    assert response.json()["bio"] == payload["bio"]


def test_user_a_cannot_update_user_b(
    client: TestClient,
    active_user: SafeAuthenticatedUser,
) -> None:
    other_id = str(uuid4())
    public_id = str(uuid4())
    with Session(engine) as session, session.begin():
        session.add(
            User(
                id=other_id,
                email=f"phase6-other-{other_id}@example.test",
                password_hash="not-used",
            )
        )
        session.add(
            UserProfile(
                user_id=other_id,
                public_id=public_id,
                display_name="Other User",
                city="Beijing",
            )
        )
    try:
        response = client.patch(
            "/api/v1/profile/me",
            json={"display_name": "Owner Update"},
        )
        assert response.status_code == 200
        with Session(engine) as session:
            other = session.scalar(select(UserProfile).where(UserProfile.user_id == other_id))
            assert other is not None
            assert other.display_name == "Other User"
            assert other.public_id == public_id
            assert other.user_id != active_user.id
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.id == other_id))


@pytest.mark.parametrize(
    "inactive_status",
    [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED],
)
def test_public_profile_is_safe_and_hidden_until_complete(
    client: TestClient,
    active_user: SafeAuthenticatedUser,
    inactive_status: AccountStatus,
) -> None:
    profile = client.get("/api/v1/profile/me").json()
    assert client.get(f"/api/v1/profiles/{profile['public_id']}").status_code == 404

    client.patch(
        "/api/v1/profile/me",
        json={"display_name": "Public Person", "bio": "Hello", "city": "Hangzhou"},
    )
    client.post("/api/v1/profile/onboarding/complete", json={})
    response = client.get(f"/api/v1/profiles/{profile['public_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Public Person"
    assert set(body).isdisjoint(
        {"id", "user_id", "email", "phone_number", "account_status", "roles"}
    )

    with Session(engine) as session, session.begin():
        user = session.get(User, active_user.id)
        assert user is not None
        user.account_status = inactive_status
    assert client.get(f"/api/v1/profiles/{profile['public_id']}").status_code == 404


def test_unknown_and_malformed_public_ids_are_safe(client: TestClient) -> None:
    unknown = client.get(f"/api/v1/profiles/{uuid4()}")
    malformed = client.get("/api/v1/profiles/not-a-uuid")

    assert unknown.status_code == 404
    assert malformed.status_code == 422
    assert "not-a-uuid" not in malformed.text


def test_profile_write_limit_returns_retry_after(client: TestClient) -> None:
    original = profile_write_ip_limiter.max_requests
    profile_write_ip_limiter.max_requests = 1
    try:
        assert client.patch("/api/v1/profile/me", json={"display_name": "First Name"}).status_code == 200
        limited = client.patch(
            "/api/v1/profile/me",
            json={"display_name": "Second Name"},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
    finally:
        profile_write_ip_limiter.max_requests = original

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1


def test_unexpected_profile_failure_returns_only_generic_error(
    active_user: SafeAuthenticatedUser,
) -> None:
    class FailingService:
        def get_or_create_own(self, session: Session, *, user_id: str):
            del session, user_id
            raise RuntimeError("mysql password=secret table=user_profiles")

    app = create_app(settings)
    app.dependency_overrides[get_current_user] = lambda: active_user
    app.dependency_overrides[get_profile_service] = FailingService
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/profile/me")

    assert response.status_code == 500
    assert response.json() == {"detail": "Profile operation could not be completed."}
    assert "mysql" not in response.text.lower()
    assert "secret" not in response.text.lower()
