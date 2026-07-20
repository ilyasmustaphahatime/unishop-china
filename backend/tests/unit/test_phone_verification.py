from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.api.v1.auth.dependencies import build_sms_sender, build_tencent_sms_config
from app.common.validators import mask_phone_number
from app.core.config import Settings
from app.integrations.sms_client import (
    DisabledSmsSender,
    FakeSmsSender,
    SmsConfigurationError,
    SmsErrorCategory,
    SmsProviderError,
    TencentSmsConfig,
    TencentSmsSender,
    UnavailableSmsSender,
)
from app.schemas.auth import (
    ResendPhoneVerificationCodeRequest,
    VerifyPhoneCodeRequest,
)


def test_fake_sms_sender_captures_one_delivery_without_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    sender = FakeSmsSender()

    result = sender.send_verification_code("+8613800000000", "012345")

    assert result.delivered is True
    assert sender.deliveries == [("+8613800000000", "012345")]
    assert capsys.readouterr().out == ""


def test_sms_is_disabled_by_default() -> None:
    sender = build_sms_sender(Settings(_env_file=None))
    assert isinstance(sender, DisabledSmsSender)


def test_enabled_tencent_without_credentials_is_unavailable() -> None:
    sender = build_sms_sender(Settings(_env_file=None, sms_enabled=True))
    assert isinstance(sender, UnavailableSmsSender)


def test_missing_tencent_configuration_reports_names_only() -> None:
    with pytest.raises(SmsConfigurationError) as captured:
        build_tencent_sms_config(Settings(_env_file=None, sms_enabled=True))
    assert "TENCENT_SECRET_ID" in captured.value.missing_variables
    assert "test-key" not in str(captured.value)


def test_enabled_tencent_with_configuration_builds_adapter() -> None:
    sender = build_sms_sender(
        Settings(
            _env_file=None,
            sms_enabled=True,
            tencent_secret_id="test-id",
            tencent_secret_key="test-key",
            tencent_sms_sdk_app_id="test-app",
            tencent_sms_signature="test-signature",
            tencent_sms_template_id="test-template",
        )
    )
    assert isinstance(sender, TencentSmsSender)


def test_resend_schema_normalizes_phone_and_forbids_unknown_fields() -> None:
    request = ResendPhoneVerificationCodeRequest(phone_number="138 0000 0000")
    assert request.phone_number == "+8613800000000"
    with pytest.raises(ValidationError):
        ResendPhoneVerificationCodeRequest(phone_number="13800000000", user_id="unsafe")


@pytest.mark.parametrize("code", ["12345", "1234567", "123 45", "１２３４５６", "ABC123", 123456])
def test_verify_schema_rejects_non_six_ascii_digit_codes(code: object) -> None:
    with pytest.raises(ValidationError):
        VerifyPhoneCodeRequest(phone_number="13800000000", code=code)


def test_verify_schema_accepts_leading_zero_code() -> None:
    request = VerifyPhoneCodeRequest(phone_number="13800000000", code="012345")
    assert request.code == "012345"


def test_phone_masking_keeps_only_safe_prefix_and_suffix() -> None:
    assert mask_phone_number("+8613800000000") == "+86******0000"


def test_tencent_timeout_maps_to_safe_provider_error() -> None:
    class TimeoutClient:
        def SendSms(self, request: object) -> None:
            raise TimeoutError

    config = TencentSmsConfig(
        secret_id=Settings(_env_file=None, tencent_secret_id="id").tencent_secret_id,
        secret_key=Settings(_env_file=None, tencent_secret_key="key").tencent_secret_key,
        sdk_app_id="app",
        signature="signature",
        template_id="template",
        region="ap-guangzhou",
        endpoint="sms.tencentcloudapi.com",
        timeout_seconds=1,
    )
    sender = TencentSmsSender(config, client_factory=lambda *_: TimeoutClient())
    with pytest.raises(SmsProviderError) as captured:
        sender.send_verification_code("+8613800000000", "123456")
    assert captured.value.category is SmsErrorCategory.TIMEOUT


def test_fake_provider_error_does_not_expose_otp_or_phone() -> None:
    sender = FakeSmsSender(fail=True)
    with pytest.raises(SmsProviderError) as captured:
        sender.send_verification_code("+8613800000000", "123456")
    message = str(captured.value)
    assert "123456" not in message
    assert "+8613800000000" not in message


def test_datetime_import_is_timezone_aware() -> None:
    assert datetime.now(timezone.utc).tzinfo is timezone.utc
