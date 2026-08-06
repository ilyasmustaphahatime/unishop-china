from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.common.enums import AccountStatus, UserRoleType
from app.core.exceptions import InvalidCredentialsError
from app.core.security import hash_rate_limit_identifier
from app.schemas.auth import LoginRequest
from app.services.auth_service import AuthenticationService
from app.services.refresh_session_service import AuthCookieMaterial


class FakeUserRepository:
    def __init__(self, user: object | None) -> None:
        self.user = user
        self.email_lookups: list[str] = []
        self.phone_lookups: list[str] = []

    def get_by_email(self, _session: object, email: str) -> object | None:
        self.email_lookups.append(email)
        return self.user

    def get_by_phone(self, _session: object, phone: str) -> object | None:
        self.phone_lookups.append(phone)
        return self.user

    def get_by_id(self, _session: object, _user_id: str) -> object | None:
        return self.user


class FakeRoleRepository:
    def list_roles_for_user(self, _session: object, _user_id: str) -> list[UserRoleType]:
        return [UserRoleType.BUYER]


class FakeTokenService:
    expires_in_seconds = 900

    def create_access_token(self, _user_id: str) -> str:
        return "synthetic-unit-token"


class FakeTransaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class FakeSession:
    def in_transaction(self) -> bool:
        return False

    def begin(self) -> FakeTransaction:
        return FakeTransaction()


class FakeRefreshSessionService:
    def create_login_session(self, _session: object, *, user_id: str) -> AuthCookieMaterial:
        assert user_id
        return AuthCookieMaterial("synthetic-refresh", "synthetic-csrf", 604800)


def active_user(**overrides: object) -> object:
    values = {
        "id": str(uuid4()),
        "email": "user@example.com",
        "phone_number": "+8613800000000",
        "password_hash": "stored-password-hash",
        "email_verified": False,
        "phone_verified": False,
        "account_status": AccountStatus.ACTIVE,
        "created_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("identifier", "normalized"),
    [
        ("  USER@EXAMPLE.COM ", "user@example.com"),
        ("13800000000", "+8613800000000"),
        ("0086 13800000000", "+8613800000000"),
    ],
)
def test_login_schema_normalizes_supported_identifiers(identifier: str, normalized: str) -> None:
    request = LoginRequest(identifier=identifier, password="weak")
    assert request.identifier == normalized
    assert request.password == "weak"


def test_login_schema_preserves_password_whitespace() -> None:
    request = LoginRequest(identifier="user@example.com", password="  password  ")
    assert request.password == "  password  "


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "password"},
        {"identifier": "user@example.com"},
        {"identifier": "not-an-identifier", "password": "password"},
        {"identifier": "user@example.com", "password": "x" * 129},
        {"identifier": "user@example.com", "password": "password", "role": "ADMIN"},
        {"identifier": "user@example.com", "password": "password", "roles": ["ADMIN"]},
        {"identifier": "user@example.com", "password": "password", "is_admin": True},
        {
            "identifier": "user@example.com",
            "password": "password",
            "account_status": "ACTIVE",
        },
        {"identifier": "user@example.com", "password": "password", "access_token": "x"},
    ],
)
def test_login_schema_rejects_invalid_or_extra_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(payload)


def test_authentication_accepts_correct_password_and_returns_safe_user() -> None:
    user = active_user()
    repository = FakeUserRepository(user)
    verification_calls: list[tuple[str, str]] = []

    def verifier(password: str, password_hash: str) -> bool:
        verification_calls.append((password, password_hash))
        return True

    service = AuthenticationService(
        user_repository=repository,
        role_repository=FakeRoleRepository(),
        token_service=FakeTokenService(),
        refresh_session_service=FakeRefreshSessionService(),
        password_verifier=verifier,
        dummy_password_hash="dummy-hash",
    )
    result = service.authenticate_user_and_create_access_token(
        FakeSession(), LoginRequest(identifier="USER@EXAMPLE.COM", password="submitted")
    )

    assert verification_calls == [("submitted", "stored-password-hash")]
    assert repository.email_lookups == ["user@example.com"]
    assert result.access_token == "synthetic-unit-token"
    assert result.expires_in == 900
    assert result.user.roles == [UserRoleType.BUYER]
    assert not hasattr(result.user, "password_hash")


def test_wrong_password_returns_generic_internal_failure() -> None:
    service = AuthenticationService(
        user_repository=FakeUserRepository(active_user()),
        role_repository=FakeRoleRepository(),
        token_service=FakeTokenService(),
        password_verifier=lambda _password, _password_hash: False,
    )
    with pytest.raises(InvalidCredentialsError):
        service.authenticate_user_and_create_access_token(
            FakeSession(), LoginRequest(identifier="user@example.com", password="wrong")
        )


def test_unknown_user_uses_dummy_verification_path() -> None:
    calls: list[tuple[str, str]] = []

    def verifier(password: str, password_hash: str) -> bool:
        calls.append((password, password_hash))
        return False

    service = AuthenticationService(
        user_repository=FakeUserRepository(None),
        role_repository=FakeRoleRepository(),
        token_service=FakeTokenService(),
        password_verifier=verifier,
        dummy_password_hash="controlled-dummy-hash",
    )
    with pytest.raises(InvalidCredentialsError):
        service.authenticate_user_and_create_access_token(
            FakeSession(), LoginRequest(identifier="unknown@example.com", password="submitted")
        )
    assert calls == [("submitted", "controlled-dummy-hash")]


@pytest.mark.parametrize(
    "account_status",
    [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED],
)
def test_inactive_accounts_receive_generic_failure(account_status: AccountStatus) -> None:
    service = AuthenticationService(
        user_repository=FakeUserRepository(active_user(account_status=account_status)),
        role_repository=FakeRoleRepository(),
        token_service=FakeTokenService(),
        password_verifier=lambda _password, _password_hash: True,
    )
    with pytest.raises(InvalidCredentialsError):
        service.authenticate_user_and_create_access_token(
            FakeSession(), LoginRequest(identifier="user@example.com", password="correct")
        )


def test_identifier_limiter_key_is_secret_keyed_and_contains_no_identifier() -> None:
    identifier = "user@example.com"
    key = hash_rate_limit_identifier(identifier, "test-only-rate-limit-secret")
    assert identifier not in key
    assert key == hash_rate_limit_identifier(identifier, "test-only-rate-limit-secret")
    assert key != hash_rate_limit_identifier(identifier, "different-test-secret")
