from fastapi import Depends

from app.core.config import Settings, settings
from app.integrations.sms_client import (
    DisabledSmsSender,
    SmsConfigurationError,
    SmsSender,
    TencentSmsConfig,
    TencentSmsSender,
    UnavailableSmsSender,
)
from app.integrations.development_fake_sms import (
    DevelopmentFakeSmsSender,
    DevelopmentFakeSmsStore,
    development_fake_sms_store,
)
from app.services.auth_service import RegistrationService
from app.services.phone_verification_service import PhoneVerificationService


def _secret_present(value: object) -> bool:
    return value is not None and bool(value.get_secret_value().strip())


def build_sms_sender(
    config: Settings,
    *,
    fake_store: DevelopmentFakeSmsStore | None = None,
) -> SmsSender:
    if not config.sms_enabled:
        return DisabledSmsSender()
    provider = config.sms_provider.strip().lower()
    if provider == "fake":
        if config.app_env.strip().lower() != "development":
            return UnavailableSmsSender()
        return DevelopmentFakeSmsSender(fake_store or development_fake_sms_store)
    if provider != "tencent":
        return UnavailableSmsSender()

    try:
        tencent_config = build_tencent_sms_config(config)
    except SmsConfigurationError:
        return UnavailableSmsSender()
    return TencentSmsSender(tencent_config)


def build_tencent_sms_config(config: Settings) -> TencentSmsConfig:
    checks = {
        "TENCENT_SECRET_ID": _secret_present(config.tencent_secret_id),
        "TENCENT_SECRET_KEY": _secret_present(config.tencent_secret_key),
        "TENCENT_SMS_SDK_APP_ID": bool((config.tencent_sms_sdk_app_id or "").strip()),
        "TENCENT_SMS_SIGNATURE": bool((config.tencent_sms_signature or "").strip()),
        "TENCENT_SMS_TEMPLATE_ID": bool((config.tencent_sms_template_id or "").strip()),
    }
    missing = [name for name, present in checks.items() if not present]
    if missing:
        raise SmsConfigurationError(missing)
    return TencentSmsConfig(
        secret_id=config.tencent_secret_id,
        secret_key=config.tencent_secret_key,
        sdk_app_id=config.tencent_sms_sdk_app_id.strip(),
        signature=config.tencent_sms_signature.strip(),
        template_id=config.tencent_sms_template_id.strip(),
        region=config.tencent_sms_region,
        endpoint=config.tencent_sms_endpoint,
        timeout_seconds=config.sms_request_timeout_seconds,
    )


def get_sms_sender() -> SmsSender:
    return build_sms_sender(settings)


def get_registration_service(
    sms_sender: SmsSender = Depends(get_sms_sender),
) -> RegistrationService:
    return RegistrationService(
        verification_code_hash_secret=settings.verification_code_hash_secret,
        sms_sender=sms_sender,
    )


def get_phone_verification_service(
    sms_sender: SmsSender = Depends(get_sms_sender),
) -> PhoneVerificationService:
    return PhoneVerificationService(
        sms_sender=sms_sender,
        verification_code_hash_secret=settings.verification_code_hash_secret,
    )
