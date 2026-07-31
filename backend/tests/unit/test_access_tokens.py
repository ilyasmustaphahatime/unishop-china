from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.core.config import AuthenticationConfigurationError, Settings
from app.core.exceptions import TokenValidationError
from app.services.token_service import AccessTokenService
from app.main import create_app

TEST_SECRET = "phase-4a-unit-test-jwt-secret-with-more-than-thirty-two-characters"


def token_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "jwt_secret_key": TEST_SECRET,
        "jwt_algorithm": "HS256",
        "access_token_expire_minutes": 15,
        "jwt_issuer": "unishop-china-api",
        "jwt_audience": "unishop-china-web",
        "jwt_clock_skew_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def required_claims(user_id: str, **overrides: object) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    claims: dict[str, object] = {
        "sub": user_id,
        "type": "access",
        "jti": "synthetic-test-token-id",
        "iss": "unishop-china-api",
        "aud": "unishop-china-web",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=15),
    }
    claims.update(overrides)
    return claims


def encode_claims(claims: dict[str, object], secret: str = TEST_SECRET) -> str:
    return jwt.encode(claims, secret, algorithm="HS256")


def test_valid_access_token_has_required_safe_claims_and_decodes() -> None:
    user_id = str(uuid4())
    service = AccessTokenService(token_settings(), token_id_provider=lambda: "unique-test-jti")
    token = service.create_access_token(user_id)
    decoded = service.decode_access_token(token)
    payload = jwt.decode(token, options={"verify_signature": False})

    assert decoded.subject == user_id
    assert decoded.token_id == "unique-test-jti"
    assert service.expires_in_seconds == 900
    assert {"sub", "type", "jti", "iss", "aud", "iat", "nbf", "exp"} <= payload.keys()
    assert payload["type"] == "access"
    assert {
        "password",
        "password_hash",
        "otp",
        "code_hash",
        "jwt_secret",
        "roles",
        "refresh_token",
        "passport",
    }.isdisjoint(payload)


def test_access_tokens_receive_unique_jti_values() -> None:
    service = AccessTokenService(token_settings())
    user_id = str(uuid4())
    first = service.decode_access_token(service.create_access_token(user_id))
    second = service.decode_access_token(service.create_access_token(user_id))
    assert first.token_id != second.token_id


@pytest.mark.parametrize(
    "claims",
    [
        required_claims(str(uuid4()), exp=datetime.now(timezone.utc) - timedelta(seconds=1)),
        required_claims(str(uuid4()), iss="wrong-issuer"),
        required_claims(str(uuid4()), aud="wrong-audience"),
        required_claims(str(uuid4()), type="refresh"),
        {key: value for key, value in required_claims(str(uuid4())).items() if key != "sub"},
        required_claims("not-a-uuid"),
    ],
)
def test_invalid_claims_are_rejected(claims: dict[str, object]) -> None:
    service = AccessTokenService(token_settings())
    with pytest.raises(TokenValidationError):
        service.decode_access_token(encode_claims(claims))


def test_wrong_signature_is_rejected() -> None:
    service = AccessTokenService(token_settings())
    token = encode_claims(required_claims(str(uuid4())), "different-synthetic-secret-value")
    with pytest.raises(TokenValidationError):
        service.decode_access_token(token)


def test_modified_token_is_rejected() -> None:
    service = AccessTokenService(token_settings())
    token = service.create_access_token(str(uuid4()))
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    modified = ".".join((header, payload, replacement + signature[1:]))
    with pytest.raises(TokenValidationError):
        service.decode_access_token(modified)


@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_malformed_token_is_rejected(token: str) -> None:
    with pytest.raises(TokenValidationError):
        AccessTokenService(token_settings()).decode_access_token(token)


@pytest.mark.parametrize(
    "overrides",
    [
        {"jwt_secret_key": "short"},
        {"jwt_secret_key": "replace_with_secure_secret_that_is_long_enough"},
        {"jwt_algorithm": "none"},
        {"jwt_algorithm": "RS256"},
        {"jwt_issuer": ""},
        {"jwt_audience": ""},
    ],
)
def test_unsafe_token_configuration_fails(overrides: dict[str, object]) -> None:
    with pytest.raises(AuthenticationConfigurationError):
        AccessTokenService(token_settings(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [{"jwt_secret_key": None}, {"jwt_secret_key": "weak"}, {"jwt_algorithm": "none"}],
)
def test_application_startup_rejects_unsafe_jwt_configuration(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(AuthenticationConfigurationError):
        create_app(token_settings(**overrides))
