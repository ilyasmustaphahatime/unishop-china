from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import socket

from fastapi.testclient import TestClient
import pytest

from app.api.v1.auth.dependencies import build_password_reset_delivery_provider
from app.core.config import Settings, UnsafeRuntimeConfigurationError
from app.core.security import (
    hash_password_reset_code,
    hash_verification_code,
    verify_password_reset_code,
)
from app.integrations.password_reset_delivery import (
    DevelopmentFakePasswordResetDeliveryProvider,
    DevelopmentFakePasswordResetStore,
    DisabledPasswordResetDeliveryProvider,
)
from app.main import create_app
from app.schemas.auth import ForgotPasswordRequest

TEST_JWT_SECRET = "phase-5a-test-jwt-secret-with-more-than-thirty-two-characters"
TEST_CODE_SECRET = "phase-5a-test-code-secret-with-more-than-thirty-two-characters"


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
        "password_reset_delivery_provider": "disabled",
        "enable_fake_password_reset_dev_inbox": False,
        "frontend_url": "http://localhost:5173",
    }
    values.update(overrides)
    return Settings(**values)


def build_store(clock: MutableClock, *, max_messages: int = 10):
    return DevelopmentFakePasswordResetStore(
        identifier_secret=TEST_JWT_SECRET,
        delivery_delay_seconds=0,
        ttl_seconds=600,
        max_messages=max_messages,
        now_provider=clock,
    )


@pytest.mark.parametrize(
    ("raw", "normalized", "kind"),
    [
        ("  PERSON@Example.COM ", "person@example.com", "email"),
        ("13800000000", "+8613800000000", "phone"),
        ("0086 13800000000", "+8613800000000", "phone"),
    ],
)
def test_forgot_password_schema_reuses_normalization(
    raw: str,
    normalized: str,
    kind: str,
) -> None:
    request = ForgotPasswordRequest(identifier=raw)

    assert request.identifier == normalized
    assert request.identifier_kind == kind


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"identifier": ""},
        {"identifier": "not-an-identifier"},
        {"identifier": "person@example.com\u202e"},
        {"identifier": "a" * 256},
        {"identifier": "person@example.com", "user_id": "forbidden"},
        {"identifier": "person@example.com", "new_password": "forbidden"},
        {"identifier": "person@example.com", "code": "123456"},
    ],
)
def test_forgot_password_schema_rejects_invalid_or_privileged_input(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ForgotPasswordRequest.model_validate(payload)


def test_reset_code_hash_is_domain_separated_and_constant_time_verifiable() -> None:
    code = "123456"
    reset_hash = hash_password_reset_code(code, TEST_CODE_SECRET)

    assert len(reset_hash) == 64
    assert reset_hash != code
    assert reset_hash != hash_verification_code(code, TEST_CODE_SECRET)
    assert verify_password_reset_code(code, reset_hash, TEST_CODE_SECRET)
    assert not verify_password_reset_code("654321", reset_hash, TEST_CODE_SECRET)


@pytest.mark.parametrize(
    "overrides",
    [
        {"verification_code_hash_secret": None},
        {"verification_code_hash_secret": "weak"},
        {"verification_code_hash_secret": "replace_with_a_real_secret_value_that_is_long"},
        {"password_reset_delivery_provider": "fake"},
        {"enable_fake_password_reset_dev_inbox": True},
        {"password_reset_delivery_provider": "unsupported"},
    ],
)
def test_production_rejects_unsafe_password_reset_configuration(
    overrides: dict[str, object],
) -> None:
    production = {
        "app_env": "production",
        "frontend_url": "https://shop.example.test",
        "refresh_cookie_secure": True,
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
    }
    production.update(overrides)

    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(reset_settings(**production))


def test_development_fake_inbox_requires_fake_provider_and_loopback_policy() -> None:
    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(
            reset_settings(
                enable_fake_password_reset_dev_inbox=True,
                password_reset_delivery_provider="disabled",
            )
        )
    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(
            reset_settings(
                enable_fake_password_reset_dev_inbox=True,
                password_reset_delivery_provider="fake",
                fake_password_reset_localhost_only=False,
            )
        )


def test_delivery_builder_never_enables_fake_provider_outside_development() -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock)

    development = build_password_reset_delivery_provider(
        reset_settings(password_reset_delivery_provider="fake"),
        fake_store=store,
    )
    production = build_password_reset_delivery_provider(
        reset_settings(
            app_env="production",
            refresh_cookie_secure=True,
            frontend_url="https://shop.example.test",
            password_reset_delivery_provider="fake",
        ),
        fake_store=store,
    )

    assert isinstance(development, DevelopmentFakePasswordResetDeliveryProvider)
    assert isinstance(production, DisabledPasswordResetDeliveryProvider)


def test_fake_delivery_is_memory_only_hashed_by_identifier_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock, max_messages=2)
    provider = DevelopmentFakePasswordResetDeliveryProvider(store)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    identifiers = [f"person{index}@example.com" for index in range(3)]
    for identifier in identifiers:
        result = provider.deliver_reset_code(
            identifier=identifier,
            identifier_kind="email",
            code="123456",
            expires_at=clock.now + timedelta(minutes=10),
        )
        assert result.delivered

    assert store.message_count() == 2
    assert store.latest_available(identifiers[0]) is None
    message = store.latest_available(identifiers[-1])
    assert message is not None
    assert identifiers[-1] not in message.identifier_reference
    assert capsys.readouterr() == ("", "")


def test_fake_store_expires_and_consumes_messages() -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock)
    message = store.add(
        identifier="person@example.com",
        identifier_kind="email",
        code="123456",
        expires_at=clock.now + timedelta(minutes=10),
    )

    assert store.latest_available("person@example.com") == message
    assert store.consume_message(message.message_id)
    assert store.latest_available("person@example.com") is None

    store.add(
        identifier="person@example.com",
        identifier_kind="email",
        code="654321",
        expires_at=clock.now + timedelta(seconds=30),
    )
    clock.advance(31)
    assert store.latest_available("person@example.com") is None


def test_fake_inbox_route_is_development_only_loopback_and_identifier_scoped() -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock)
    store.add(
        identifier="person@example.com",
        identifier_kind="email",
        code="123456",
        expires_at=clock.now + timedelta(minutes=10),
    )
    config = reset_settings(
        password_reset_delivery_provider="fake",
        enable_fake_password_reset_dev_inbox=True,
    )
    application = create_app(config, fake_password_reset_store=store)

    with TestClient(application, client=("127.0.0.1", 51000)) as local:
        response = local.get(
            "/api/v1/dev/fake-password-reset/latest",
            params={"identifier": "PERSON@example.com"},
        )
        assert response.status_code == 200
        assert response.json()["code"] == "123456"
        assert "person@example.com" not in response.text
        assert response.headers["cache-control"] == "no-store"

    with TestClient(application, client=("198.51.100.50", 51000)) as remote:
        rejected = remote.get(
            "/api/v1/dev/fake-password-reset/latest",
            params={"identifier": "person@example.com"},
            headers={"X-Forwarded-For": "127.0.0.1"},
        )
        assert rejected.status_code == 403

    production = create_app(
        reset_settings(
            app_env="production",
            frontend_url="https://shop.example.test",
            refresh_cookie_secure=True,
            password_reset_delivery_provider="disabled",
            enable_fake_password_reset_dev_inbox=False,
        )
    )
    assert not any("fake-password-reset" in path for path in production.openapi()["paths"])
