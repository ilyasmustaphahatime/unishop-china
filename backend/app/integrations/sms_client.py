"""Provider-neutral SMS delivery with test and Tencent implementations."""

from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import SecretStr


@dataclass(frozen=True, slots=True)
class SmsDeliveryResult:
    delivered: bool
    provider: str
    request_id: str | None = None


class SmsErrorCategory(StrEnum):
    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class SmsProviderError(RuntimeError):
    def __init__(self, category: SmsErrorCategory) -> None:
        super().__init__(f"SMS delivery failed ({category.value}).")
        self.category = category


class SmsConfigurationError(RuntimeError):
    def __init__(self, missing_variables: list[str]) -> None:
        names = ", ".join(sorted(missing_variables))
        super().__init__(f"Missing SMS configuration variables: {names}")
        self.missing_variables = tuple(sorted(missing_variables))


class SmsSender(Protocol):
    enabled: bool
    available: bool

    def send_verification_code(self, phone_number: str, code: str) -> SmsDeliveryResult: ...


class FakeSmsSender:
    """Network-free sender explicitly injected by tests."""

    enabled = True
    available = True

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deliveries: list[tuple[str, str]] = []

    def send_verification_code(self, phone_number: str, code: str) -> SmsDeliveryResult:
        if self.fail:
            raise SmsProviderError(SmsErrorCategory.UNAVAILABLE)
        self.deliveries.append((phone_number, code))
        return SmsDeliveryResult(delivered=True, provider="fake", request_id="fake-request")


class DisabledSmsSender:
    enabled = False
    available = False

    def send_verification_code(self, phone_number: str, code: str) -> SmsDeliveryResult:
        return SmsDeliveryResult(delivered=False, provider="disabled")


class UnavailableSmsSender:
    enabled = True
    available = False

    def send_verification_code(self, phone_number: str, code: str) -> SmsDeliveryResult:
        raise SmsProviderError(SmsErrorCategory.CONFIGURATION)


@dataclass(frozen=True, slots=True)
class TencentSmsConfig:
    secret_id: SecretStr
    secret_key: SecretStr
    sdk_app_id: str
    signature: str
    template_id: str
    region: str
    endpoint: str
    timeout_seconds: int


class TencentSmsSender:
    """Tencent Cloud SMS SDK 3.0 adapter. It performs no retries."""

    enabled = True
    available = True

    def __init__(
        self,
        config: TencentSmsConfig,
        *,
        client_factory: Callable[[Any, str, Any], Any] | None = None,
    ) -> None:
        self.config = config
        self.client_factory = client_factory

    def send_verification_code(self, phone_number: str, code: str) -> SmsDeliveryResult:
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
                TencentCloudSDKException,
            )
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.sms.v20210111 import models, sms_client

            cred = credential.Credential(
                self.config.secret_id.get_secret_value(),
                self.config.secret_key.get_secret_value(),
            )
            http_profile = HttpProfile()
            http_profile.endpoint = self.config.endpoint
            http_profile.reqTimeout = self.config.timeout_seconds
            factory = self.client_factory or sms_client.SmsClient
            client = factory(
                cred,
                self.config.region,
                ClientProfile(httpProfile=http_profile),
            )
            request = models.SendSmsRequest()
            request.SmsSdkAppId = self.config.sdk_app_id
            request.SignName = self.config.signature
            request.TemplateId = self.config.template_id
            request.TemplateParamSet = [code]
            request.PhoneNumberSet = [phone_number]
            response = client.SendSms(request)
        except (TimeoutError, ConnectionError) as exc:
            raise SmsProviderError(SmsErrorCategory.TIMEOUT) from exc
        except TencentCloudSDKException as exc:
            category = (
                SmsErrorCategory.TIMEOUT
                if "timeout" in str(exc).lower()
                else SmsErrorCategory.UNAVAILABLE
            )
            raise SmsProviderError(category) from exc
        except Exception as exc:
            raise SmsProviderError(SmsErrorCategory.UNAVAILABLE) from exc

        statuses = response.SendStatusSet or []
        if len(statuses) != 1 or statuses[0].Code != "Ok":
            raise SmsProviderError(SmsErrorCategory.REJECTED)
        return SmsDeliveryResult(
            delivered=True,
            provider="tencent",
            request_id=getattr(response, "RequestId", None),
        )
