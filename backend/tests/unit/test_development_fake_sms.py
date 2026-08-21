from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1.auth.dependencies import build_sms_sender
from app.core.config import (
    Settings,
    UnsafeRuntimeConfigurationError,
    validate_runtime_security,
)
from app.integrations.development_fake_sms import (
    DevelopmentFakeSmsSender,
    DevelopmentFakeSmsStore,
)
from app.main import create_app

JWT_TEST_SECRET = "phase-4a-test-only-jwt-secret-with-more-than-thirty-two-characters"
CODE_TEST_SECRET = "phase-5a-test-only-code-secret-with-more-than-thirty-two-characters"

PHONE = "+8613800000000"


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 24, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def build_store(clock: MutableClock, *, max_messages: int = 100) -> DevelopmentFakeSmsStore:
    return DevelopmentFakeSmsStore(
        delivery_delay_seconds=3,
        ttl_seconds=600,
        max_messages=max_messages,
        now_provider=clock,
    )


def test_development_fake_sender_stores_memory_message_after_delay() -> None:
    clock = MutableClock()
    store = build_store(clock)
    sender = DevelopmentFakeSmsSender(store)

    result = sender.send_verification_code(PHONE, "123456", delivery_type="registration")

    assert result.delivered is True
    assert result.provider == "fake"
    assert store.latest_available(PHONE) is None
    clock.advance(3)
    message = store.latest_available(PHONE)
    assert message is not None
    assert message.code == "123456"
    assert message.delivery_type == "registration"


def test_development_fake_sender_does_not_log_print_or_open_network(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Development fake SMS must not open a network connection.")

    monkeypatch.setattr("socket.create_connection", fail_network)
    clock = MutableClock()
    sender = DevelopmentFakeSmsSender(build_store(clock))

    sender.send_verification_code(PHONE, "487215", delivery_type="registration")

    assert caplog.text == ""
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_new_message_supersedes_old_message_for_same_phone() -> None:
    clock = MutableClock()
    store = build_store(clock)
    first = store.add(PHONE, "123456", "registration")
    second = store.add(PHONE, "654321", "resend")
    clock.advance(3)

    latest = store.latest_available(PHONE)
    assert latest is not None and latest.message_id == second.message_id
    assert latest.message_id != first.message_id
    assert store.message_count() == 1


def test_messages_are_isolated_by_phone() -> None:
    clock = MutableClock()
    store = build_store(clock)
    other_phone = "+8613900000000"
    store.add(PHONE, "123456", "registration")
    store.add(other_phone, "654321", "registration")
    clock.advance(3)

    assert store.latest_available(PHONE).code == "123456"
    assert store.latest_available(other_phone).code == "654321"


def test_expired_message_is_removed() -> None:
    clock = MutableClock()
    store = build_store(clock)
    store.add(PHONE, "123456", "registration")
    clock.advance(601)

    assert store.latest_available(PHONE) is None
    assert store.message_count() == 0


def test_consumed_message_is_removed() -> None:
    clock = MutableClock()
    store = build_store(clock)
    sender = DevelopmentFakeSmsSender(store)
    sender.send_verification_code(PHONE, "123456")
    clock.advance(3)

    sender.consume_verification_code(PHONE, "123456")

    assert store.latest_available(PHONE) is None


def test_store_enforces_maximum_message_count() -> None:
    clock = MutableClock()
    store = build_store(clock, max_messages=2)
    store.add("+8613800000001", "111111", "registration")
    store.add("+8613800000002", "222222", "registration")
    store.add("+8613800000003", "333333", "registration")
    assert store.message_count() == 2


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_fake_provider_is_blocked_outside_development(environment: str) -> None:
    config = Settings(_env_file=None, app_env=environment, sms_provider="fake")
    with pytest.raises(UnsafeRuntimeConfigurationError) as captured:
        validate_runtime_security(config)
    assert "SMS_PROVIDER" in captured.value.unsafe_variables


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_fake_inbox_is_blocked_outside_development(environment: str) -> None:
    config = Settings(
        _env_file=None,
        app_env=environment,
        enable_fake_sms_dev_inbox=True,
        jwt_secret_key=JWT_TEST_SECRET,
    )
    with pytest.raises(UnsafeRuntimeConfigurationError) as captured:
        validate_runtime_security(config)
    assert "ENABLE_FAKE_SMS_DEV_INBOX" in captured.value.unsafe_variables


def test_non_local_fake_inbox_configuration_is_blocked() -> None:
    config = Settings(
        _env_file=None,
        app_env="development",
        enable_fake_sms_dev_inbox=True,
        fake_sms_localhost_only=False,
    )
    with pytest.raises(UnsafeRuntimeConfigurationError) as captured:
        validate_runtime_security(config)
    assert captured.value.unsafe_variables == ("FAKE_SMS_LOCALHOST_ONLY",)


def test_explicit_development_fake_configuration_builds_memory_sender() -> None:
    clock = MutableClock()
    store = build_store(clock)
    config = Settings(
        _env_file=None,
        app_env="development",
        sms_enabled=True,
        sms_provider="fake",
        enable_fake_sms_dev_inbox=True,
        jwt_secret_key=JWT_TEST_SECRET,
    )
    validate_runtime_security(config)
    assert isinstance(build_sms_sender(config, fake_store=store), DevelopmentFakeSmsSender)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_non_development_application_forces_debug_off(environment: str) -> None:
    config = Settings(
        _env_file=None,
        app_env=environment,
        app_debug=True,
        sms_enabled=False,
        sms_provider="tencent",
        enable_fake_sms_dev_inbox=False,
        jwt_secret_key=JWT_TEST_SECRET,
        verification_code_hash_secret=CODE_TEST_SECRET,
        refresh_cookie_secure=True,
    )

    application = create_app(config)

    assert application.debug is False


def test_phase_4b_cors_uses_explicit_origin_with_credentials() -> None:
    config = Settings(
        _env_file=None,
        app_env="production",
        app_debug=False,
        frontend_url="https://shop.example.test",
        sms_enabled=False,
        sms_provider="tencent",
        enable_fake_sms_dev_inbox=False,
        jwt_secret_key=JWT_TEST_SECRET,
        verification_code_hash_secret=CODE_TEST_SECRET,
        refresh_cookie_secure=True,
    )

    application = create_app(config)
    cors = next(
        middleware
        for middleware in application.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert cors.kwargs["allow_origins"] == ["https://shop.example.test"]
    assert cors.kwargs["allow_credentials"] is True
    assert "X-CSRF-Token" in cors.kwargs["allow_headers"]
