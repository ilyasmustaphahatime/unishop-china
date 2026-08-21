import pytest

from app.core.config import Settings
from app.schemas.auth import ResetPasswordRequest

VALID_PASSWORD = "NewStrongPassword456"


@pytest.mark.parametrize(
    ("raw", "normalized", "kind"),
    [
        ("  PERSON@Example.COM ", "person@example.com", "email"),
        ("13800000000", "+8613800000000", "phone"),
        ("0086 13800000000", "+8613800000000", "phone"),
    ],
)
def test_reset_schema_reuses_phase_5a_identifier_normalization(
    raw: str,
    normalized: str,
    kind: str,
) -> None:
    request = ResetPasswordRequest(
        identifier=raw,
        code="123456",
        new_password=VALID_PASSWORD,
    )

    assert request.identifier == normalized
    assert request.identifier_kind == kind


@pytest.mark.parametrize(
    "code",
    [
        "",
        "12345",
        "1234567",
        "12345a",
        " 123456",
        "123456 ",
        "１２３４５６",
        "١٢٣٤٥٦",
    ],
)
def test_reset_schema_accepts_only_six_ascii_digits(code: str) -> None:
    with pytest.raises(ValueError):
        ResetPasswordRequest(
            identifier="person@example.com",
            code=code,
            new_password=VALID_PASSWORD,
        )


@pytest.mark.parametrize(
    "new_password",
    [
        "",
        "Short1A",
        "alllowercase123",
        "ALLUPPERCASE123",
        "NoDigitsHere",
        "A" * 129 + "a1",
    ],
)
def test_reset_schema_reuses_registration_password_policy(
    new_password: str,
) -> None:
    with pytest.raises(ValueError):
        ResetPasswordRequest(
            identifier="person@example.com",
            code="123456",
            new_password=new_password,
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": "client-controlled"},
        {"role": "ADMIN"},
        {"is_admin": True},
        {"password_hash": "client-controlled"},
        {"attempts": 0},
        {"used_at": None},
        {"session_id": "client-controlled"},
    ],
)
def test_reset_schema_forbids_privileged_and_internal_fields(
    extra: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ResetPasswordRequest.model_validate(
            {
                "identifier": "person@example.com",
                "code": "123456",
                "new_password": VALID_PASSWORD,
                **extra,
            }
        )


def test_phase_5b_attempt_configuration_is_bounded() -> None:
    assert Settings(_env_file=None).password_reset_max_attempts == 5
    with pytest.raises(ValueError):
        Settings(_env_file=None, password_reset_max_attempts=0)
    with pytest.raises(ValueError):
        Settings(_env_file=None, password_reset_max_attempts=11)


def test_phase_5b_rate_limit_defaults_match_the_approved_policy() -> None:
    config = Settings(_env_file=None)

    assert config.password_reset_ip_rate_limit_requests == 10
    assert config.password_reset_ip_rate_limit_window_seconds == 900
    assert config.password_reset_identifier_rate_limit_requests == 5
    assert config.password_reset_identifier_rate_limit_window_seconds == 900
