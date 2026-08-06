import hashlib
from http.cookies import SimpleCookie

import pytest
from fastapi import Response

from app.core.auth_cookies import clear_auth_cookies, set_auth_cookies
from app.core.config import SessionConfigurationError, Settings, validate_session_configuration
from app.core.exceptions import RequestVerificationError
from app.core.session_security import (
    generate_csrf_token,
    generate_refresh_token,
    hash_csrf_token,
    hash_refresh_token,
    validate_csrf_tokens,
    validate_request_origin,
)


def session_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "development",
        "frontend_url": "http://localhost:5173",
        "refresh_cookie_secure": False,
    }
    values.update(overrides)
    return Settings(**values)


def parsed_cookies(response: Response) -> dict[str, SimpleCookie[str]]:
    parsed: dict[str, SimpleCookie[str]] = {}
    for header in response.raw_headers:
        if header[0].lower() != b"set-cookie":
            continue
        cookie: SimpleCookie[str] = SimpleCookie()
        cookie.load(header[1].decode("latin-1"))
        parsed[next(iter(cookie))] = cookie
    return parsed


def test_refresh_and_csrf_tokens_are_high_entropy_unique_and_hash_only() -> None:
    refresh_tokens = {generate_refresh_token() for _ in range(20)}
    csrf_tokens = {generate_csrf_token() for _ in range(20)}

    assert len(refresh_tokens) == len(csrf_tokens) == 20
    assert min(map(len, refresh_tokens)) >= 80
    assert min(map(len, csrf_tokens)) >= 40
    raw_refresh = next(iter(refresh_tokens))
    raw_csrf = next(iter(csrf_tokens))
    assert hash_refresh_token(raw_refresh) == hashlib.sha256(raw_refresh.encode()).hexdigest()
    assert hash_csrf_token(raw_csrf) == hashlib.sha256(raw_csrf.encode()).hexdigest()
    assert hash_refresh_token(raw_refresh) != raw_refresh
    assert hash_csrf_token(raw_csrf) != raw_csrf


def test_csrf_requires_cookie_header_and_database_binding() -> None:
    token = "synthetic-csrf-value"
    validate_csrf_tokens(
        cookie_token=token,
        header_token=token,
        stored_hash=hash_csrf_token(token),
    )

    invalid_cases = (
        (None, token, hash_csrf_token(token)),
        (token, None, hash_csrf_token(token)),
        (token, "different", hash_csrf_token(token)),
        (token, token, hash_csrf_token("different")),
    )
    for cookie, header, stored_hash in invalid_cases:
        with pytest.raises(RequestVerificationError):
            validate_csrf_tokens(
                cookie_token=cookie,
                header_token=header,
                stored_hash=stored_hash,
            )


def test_origin_policy_accepts_exact_local_origins_and_rejects_foreign_origin() -> None:
    config = session_settings()
    validate_request_origin(None, config)
    validate_request_origin("http://localhost:5173", config)
    validate_request_origin("http://127.0.0.1:5173", config)
    with pytest.raises(RequestVerificationError):
        validate_request_origin("https://foreign.example", config)


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_env": "production", "refresh_cookie_secure": False},
        {"refresh_cookie_samesite": "none", "refresh_cookie_secure": False},
        {"refresh_cookie_samesite": "unsupported"},
        {"refresh_cookie_name": ""},
        {"refresh_cookie_name": "same", "csrf_cookie_name": "same"},
        {"refresh_cookie_name": "invalid name"},
        {"refresh_cookie_path": "/api/v1/auth; Domain=example.test"},
        {"refresh_token_expire_days": 7, "refresh_session_absolute_days": 6},
        {"frontend_url": "*"},
        {"frontend_url": "https://user:password@example.test"},
    ],
)
def test_unsafe_session_configuration_is_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(SessionConfigurationError):
        validate_session_configuration(session_settings(**overrides))


def test_safe_production_configuration_is_accepted() -> None:
    validate_session_configuration(
        session_settings(
            app_env="production",
            frontend_url="https://shop.example.test",
            refresh_cookie_secure=True,
        )
    )


@pytest.mark.parametrize("secure", [False, True])
def test_cookie_helpers_apply_matching_security_and_scope(secure: bool) -> None:
    config = session_settings(refresh_cookie_secure=secure)
    response = Response()
    set_auth_cookies(
        response,
        refresh_token="synthetic-refresh-value",
        csrf_token="synthetic-csrf-value",
        max_age=1234,
        config=config,
    )
    cookies = parsed_cookies(response)
    refresh = cookies[config.refresh_cookie_name][config.refresh_cookie_name]
    csrf = cookies[config.csrf_cookie_name][config.csrf_cookie_name]

    assert refresh["httponly"] is True
    assert csrf["httponly"] == ""
    assert bool(refresh["secure"]) is secure
    assert bool(csrf["secure"]) is secure
    assert refresh["samesite"].lower() == csrf["samesite"].lower() == "lax"
    assert refresh["path"] == csrf["path"] == "/api/v1/auth"
    assert refresh["domain"] == csrf["domain"] == ""
    assert refresh["max-age"] == csrf["max-age"] == "1234"
    assert refresh["expires"] and csrf["expires"]

    cleared = Response()
    clear_auth_cookies(cleared, config)
    clear_headers = [value.decode("latin-1") for key, value in cleared.raw_headers if key == b"set-cookie"]
    assert len(clear_headers) == 2
    assert all("Path=/api/v1/auth" in value and "Max-Age=0" in value for value in clear_headers)
    assert all("synthetic" not in value for value in clear_headers)
