from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import socket

import pytest

from app.api.v1.auth.dependencies import build_email_verification_delivery_provider
from app.core.config import Settings, UnsafeRuntimeConfigurationError
from app.core.security import (
    generate_verification_code,
    hash_email_verification_code,
    hash_password_reset_code,
    hash_verification_code,
    verify_email_verification_code,
)
from app.integrations.email_verification_delivery import (
    DevelopmentFakeEmailVerificationProvider,
    DevelopmentFakeEmailVerificationStore,
    DisabledEmailVerificationDeliveryProvider,
)
from app.main import create_app
from app.schemas.auth import (
    ResendEmailVerificationCodeRequest,
    VerifyEmailCodeRequest,
)

TEST_JWT_SECRET = "phase-5d-test-jwt-secret-with-more-than-thirty-two-characters"
TEST_CODE_SECRET = "phase-5d-test-code-secret-with-more-than-thirty-two-characters"


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def email_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "app_debug": False,
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
        "email_verification_delivery_provider": "disabled",
        "enable_fake_email_verification_dev_inbox": False,
        "frontend_url": "http://localhost:5173",
    }
    values.update(overrides)
    return Settings(**values)


def build_store(clock: MutableClock, *, max_messages: int = 10):
    return DevelopmentFakeEmailVerificationStore(
        user_reference_secret=TEST_JWT_SECRET,
        delivery_delay_seconds=0,
        ttl_seconds=600,
        max_messages=max_messages,
        now_provider=clock,
    )


def test_secure_generator_produces_exactly_six_ascii_digits() -> None:
    assert generate_verification_code(lambda limit: limit - 1) == "999999"
    assert generate_verification_code(lambda _limit: 0) == "000000"
    for _ in range(100):
        code = generate_verification_code()
        assert len(code) == 6
        assert code.isascii()
        assert code.isdigit()


def test_email_hash_is_domain_separated_and_constant_time_verifiable() -> None:
    code = "123456"
    email_hash = hash_email_verification_code(code, TEST_CODE_SECRET)

    assert len(email_hash) == 64
    assert email_hash != code
    assert email_hash != hash_verification_code(code, TEST_CODE_SECRET)
    assert email_hash != hash_password_reset_code(code, TEST_CODE_SECRET)
    assert verify_email_verification_code(code, email_hash, TEST_CODE_SECRET)
    assert not verify_email_verification_code("654321", email_hash, TEST_CODE_SECRET)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"code": "12345"},
        {"code": "1234567"},
        {"code": "１２３４５６"},
        {"code": "١٢٣٤٥٦"},
        {"code": "123 56"},
        {"code": "abcdef"},
        {"code": 123456},
        {"code": "123456", "user_id": "forbidden"},
        {"code": "123456", "email": "victim@example.com"},
        {"code": "123456", "role": "ADMIN"},
        {"code": "123456", "status": "ACTIVE"},
    ],
)
def test_verify_schema_rejects_malformed_or_privileged_input(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        VerifyEmailCodeRequest.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": "forbidden"},
        {"email": "victim@example.com"},
        {"email_verified": True},
        {"role": "ADMIN"},
    ],
)
def test_resend_schema_accepts_only_an_empty_object(payload: dict[str, object]) -> None:
    ResendEmailVerificationCodeRequest.model_validate({})
    with pytest.raises(ValueError):
        ResendEmailVerificationCodeRequest.model_validate(payload)


@pytest.mark.parametrize(
    "overrides",
    [
        {"verification_code_hash_secret": None},
        {"verification_code_hash_secret": "weak"},
        {
            "verification_code_hash_secret":
                "replace_with_a_real_secret_value_that_is_long"
        },
        {"email_verification_delivery_provider": "fake"},
        {"enable_fake_email_verification_dev_inbox": True},
        {"email_verification_delivery_provider": "unsupported"},
    ],
)
def test_production_rejects_unsafe_email_verification_configuration(
    overrides: dict[str, object],
) -> None:
    production: dict[str, object] = {
        "app_env": "production",
        "frontend_url": "https://shop.example.test",
        "refresh_cookie_secure": True,
        "jwt_secret_key": TEST_JWT_SECRET,
        "verification_code_hash_secret": TEST_CODE_SECRET,
    }
    production.update(overrides)
    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(email_settings(**production))


def test_fake_inbox_requires_fake_provider_and_loopback_policy() -> None:
    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(
            email_settings(enable_fake_email_verification_dev_inbox=True)
        )
    with pytest.raises(UnsafeRuntimeConfigurationError):
        create_app(
            email_settings(
                email_verification_delivery_provider="fake",
                enable_fake_email_verification_dev_inbox=True,
                fake_email_verification_localhost_only=False,
            )
        )


def test_provider_builder_enables_fake_only_in_development() -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock)
    development = build_email_verification_delivery_provider(
        email_settings(email_verification_delivery_provider="fake"),
        fake_store=store,
    )
    production = build_email_verification_delivery_provider(
        email_settings(
            app_env="production",
            frontend_url="https://shop.example.test",
            refresh_cookie_secure=True,
            email_verification_delivery_provider="fake",
        ),
        fake_store=store,
    )

    assert isinstance(development, DevelopmentFakeEmailVerificationProvider)
    assert isinstance(production, DisabledEmailVerificationDeliveryProvider)


def test_fake_provider_is_memory_only_user_scoped_bounded_and_network_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock, max_messages=2)
    provider = DevelopmentFakeEmailVerificationProvider(store)

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    for index in range(3):
        result = provider.deliver_verification_code(
            user_id=f"user-{index}",
            email=f"person{index}@example.com",
            code=f"{index:06d}",
            expires_at=clock.now + timedelta(minutes=10),
        )
        assert result.delivered

    assert store.message_count() == 2
    assert store.latest_available("user-0") is None
    message = store.latest_available("user-2")
    assert message is not None
    assert "user-2" not in message.user_reference
    assert "person2@example.com" not in repr(message)
    assert capsys.readouterr() == ("", "")


def test_fake_store_expires_and_consumes_only_owner_messages() -> None:
    clock = MutableClock(datetime.now(timezone.utc))
    store = build_store(clock)
    message = store.add(
        user_id="user-a",
        code="123456",
        expires_at=clock.now + timedelta(seconds=30),
    )

    assert store.latest_available("user-b") is None
    assert not store.consume_message(user_id="user-b", message_id=message.message_id)
    assert store.latest_available("user-a") == message
    assert store.consume_code(user_id="user-a", code="123456")
    assert store.latest_available("user-a") is None

    store.add(
        user_id="user-a",
        code="654321",
        expires_at=clock.now + timedelta(seconds=30),
    )
    clock.advance(31)
    assert store.latest_available("user-a") is None
