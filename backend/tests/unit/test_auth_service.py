from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.common.enums import AccountStatus, UserRoleType
from app.common.validators import normalize_chinese_phone_number
from app.core.security import (
    generate_verification_code,
    hash_password,
    hash_verification_code,
    verify_password,
    verify_verification_code,
)
from app.schemas.auth import RegisterRequest, RegisterResponse

TEST_CODE_SECRET = "unit-test-verification-code-secret-with-enough-entropy"


def test_register_request_accepts_email_only() -> None:
    request = RegisterRequest(email="user@example.com", password="StrongPassword123")
    assert str(request.email) == "user@example.com"
    assert request.phone_number is None


def test_register_request_accepts_phone_only() -> None:
    request = RegisterRequest(phone_number="13800000000", password="StrongPassword123")
    assert request.email is None
    assert request.phone_number == "+8613800000000"


def test_register_request_accepts_email_and_phone() -> None:
    request = RegisterRequest(
        email="user@example.com",
        phone_number="13800000000",
        password="StrongPassword123",
    )
    assert str(request.email) == "user@example.com"
    assert request.phone_number == "+8613800000000"


def test_register_request_requires_email_or_phone() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(password="StrongPassword123")


def test_register_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="StrongPassword123")


@pytest.mark.parametrize(
    "phone_number",
    [
        "12345",
        "138000000000",
        "+8610000000000",
        "phone-number",
        "",
        "+14155552671",
    ],
    ids=["too-short", "too-long", "impossible", "letters", "empty", "unsupported-country"],
)
def test_register_request_rejects_invalid_phone(phone_number: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(phone_number=phone_number, password="StrongPassword123")


@pytest.mark.parametrize(
    "field",
    [
        "role",
        "roles",
        "is_admin",
        "account_status",
        "phone_verified",
        "email_verified",
        "password_hash",
        "created_at",
        "updated_at",
    ],
)
def test_register_request_rejects_privileged_unknown_fields(field: str) -> None:
    payload = {
        "email": "user@example.com",
        "password": "StrongPassword123",
        field: "ADMIN",
    }
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(payload)


@pytest.mark.parametrize(
    "password",
    [
        "Short1",
        "A" + "a" * 127 + "1",
        "lowercase123",
        "UPPERCASE123",
        "NoDigitsHere",
    ],
    ids=["too-short", "too-long", "no-uppercase", "no-lowercase", "no-digit"],
)
def test_register_request_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password=password)


def test_email_is_trimmed_and_lowercased() -> None:
    request = RegisterRequest(
        email="  ILYAS@EXAMPLE.COM  ",
        password="StrongPassword123",
    )
    assert str(request.email) == "ilyas@example.com"


def test_password_whitespace_is_not_trimmed() -> None:
    password = " StrongPassword123 "
    request = RegisterRequest(email="user@example.com", password=password)
    assert request.password == password


@pytest.mark.parametrize(
    "phone_input",
    ["13800000000", "+86 138 0000 0000", "0086 13800000000"],
)
def test_phone_is_normalized_to_e164(phone_input: str) -> None:
    assert normalize_chinese_phone_number(phone_input) == "+8613800000000"


def test_phone_normalization_rejects_impossible_number() -> None:
    with pytest.raises(ValueError):
        normalize_chinese_phone_number("+8610000000000")


def test_password_hash_is_not_raw_and_verifies() -> None:
    password = "StrongPassword123"
    password_digest = hash_password(password)

    assert password_digest != password
    assert password_digest.startswith("$argon2id$")
    assert verify_password(password, password_digest) is True
    assert verify_password("WrongPassword123", password_digest) is False


def test_register_response_cannot_expose_hash_fields() -> None:
    response = RegisterResponse(
        id="00000000-0000-0000-0000-000000000001",
        email="user@example.com",
        phone_number=None,
        phone_verified=False,
        email_verified=False,
        account_status=AccountStatus.ACTIVE,
        roles=[UserRoleType.BUYER],
        phone_verification_required=False,
        created_at=datetime.now(timezone.utc),
    )
    response_fields = response.model_dump().keys()

    assert "password" not in response_fields
    assert "password_hash" not in response_fields
    assert "code" not in response_fields
    assert "code_hash" not in response_fields


def test_verification_code_contains_six_numeric_digits() -> None:
    code = generate_verification_code()
    assert len(code) == 6
    assert code.isdigit()


def test_verification_code_generator_is_deterministic_when_injected() -> None:
    assert generate_verification_code(lambda upper_bound: 42) == "000042"


def test_verification_code_is_hashed_and_verifiable() -> None:
    raw_code = "123456"
    code_hash = hash_verification_code(raw_code, TEST_CODE_SECRET)

    assert code_hash != raw_code
    assert verify_verification_code(raw_code, code_hash, TEST_CODE_SECRET) is True
    assert verify_verification_code("654321", code_hash, TEST_CODE_SECRET) is False
