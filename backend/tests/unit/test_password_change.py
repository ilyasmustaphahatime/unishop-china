import pytest

from app.core.config import Settings
from app.schemas.auth import ChangePasswordRequest

CURRENT_PASSWORD = "CurrentStrongPassword123"
NEW_PASSWORD = "NewStrongPassword456"


def test_change_password_schema_accepts_only_current_and_new_password() -> None:
    request = ChangePasswordRequest(
        current_password=CURRENT_PASSWORD,
        new_password=NEW_PASSWORD,
    )

    assert request.current_password == CURRENT_PASSWORD
    assert request.new_password == NEW_PASSWORD


@pytest.mark.parametrize(
    "new_password",
    [
        "",
        "Short1A",
        "alllowercase123",
        "ALLUPPERCASE123",
        "NoDigitsHere",
        "A" * 128 + "a1",
    ],
)
def test_change_password_reuses_registration_password_policy(
    new_password: str,
) -> None:
    with pytest.raises(ValueError):
        ChangePasswordRequest(
            current_password=CURRENT_PASSWORD,
            new_password=new_password,
        )


@pytest.mark.parametrize(
    "current_password",
    ["", "A" * 129, 123, None, [CURRENT_PASSWORD]],
)
def test_current_password_is_strict_and_bounded(current_password: object) -> None:
    with pytest.raises(ValueError):
        ChangePasswordRequest.model_validate(
            {
                "current_password": current_password,
                "new_password": NEW_PASSWORD,
            }
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": "client-controlled"},
        {"email": "victim@example.com"},
        {"phone": "+8613800000000"},
        {"role": "ADMIN"},
        {"is_admin": True},
        {"password_hash": "client-controlled"},
        {"session_id": "client-controlled"},
        {"refresh_token": "client-controlled"},
        {"access_token": "client-controlled"},
        {"account_status": "ACTIVE"},
        {"verification_status": True},
    ],
)
def test_change_password_forbids_identity_and_privileged_fields(
    extra: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        ChangePasswordRequest.model_validate(
            {
                "current_password": CURRENT_PASSWORD,
                "new_password": NEW_PASSWORD,
                **extra,
            }
        )


def test_phase_5c_rate_limit_defaults_match_approved_policy() -> None:
    config = Settings(_env_file=None)

    assert config.password_change_ip_rate_limit_requests == 10
    assert config.password_change_ip_rate_limit_window_seconds == 900
    assert config.password_change_user_rate_limit_requests == 5
    assert config.password_change_user_rate_limit_window_seconds == 900
    assert config.password_change_rate_limit_max_keys == 10000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("password_change_ip_rate_limit_requests", 0),
        ("password_change_user_rate_limit_requests", 0),
        ("password_change_ip_rate_limit_window_seconds", 59),
        ("password_change_user_rate_limit_window_seconds", 59),
        ("password_change_rate_limit_max_keys", 99),
    ],
)
def test_phase_5c_rate_limit_configuration_is_bounded(
    field: str,
    value: int,
) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})
