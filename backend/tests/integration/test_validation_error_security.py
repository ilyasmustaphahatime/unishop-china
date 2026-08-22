import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides.clear()
    with TestClient(
        app,
        client=("198.51.100.83", 54000),
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(child, key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, key) for child in value)
    return False


def _assert_safe_validation_response(response: object, marker: str) -> None:
    assert response.status_code == 422
    payload = response.json()
    assert marker not in json.dumps(payload, ensure_ascii=False)
    assert not _contains_key(payload, "input")
    assert not _contains_key(payload, "ctx")
    assert not _contains_key(payload, "url")
    assert isinstance(payload.get("detail"), list)
    assert payload["detail"]
    for error in payload["detail"]:
        assert set(error) == {"type", "loc", "msg"}
        assert isinstance(error["type"], str)
        assert isinstance(error["loc"], list)
        assert isinstance(error["msg"], str)


@pytest.mark.parametrize(
    ("path", "payload", "marker"),
    [
        (
            "/api/v1/auth/register",
            {
                "email": "validation-audit@example.com",
                "password": "SyntheticPasswordMarker",
            },
            "SyntheticPasswordMarker",
        ),
        (
            "/api/v1/auth/login",
            {
                "identifier": "validation-audit@example.com",
                "password": "Aa1" + "z" * 130,
            },
            "Aa1" + "z" * 130,
        ),
        (
            "/api/v1/auth/password/forgot",
            {"identifier": "SyntheticInvalidIdentifierMarker"},
            "SyntheticInvalidIdentifierMarker",
        ),
        (
            "/api/v1/auth/password/reset",
            {
                "identifier": "validation-audit@example.com",
                "code": "123456",
                "new_password": "SyntheticPasswordMarker",
            },
            "SyntheticPasswordMarker",
        ),
        (
            "/api/v1/auth/password/reset",
            {
                "identifier": "validation-audit@example.com",
                "code": "１２３４５６",
                "new_password": "SyntheticValid123",
            },
            "１２３４５６",
        ),
        (
            "/api/v1/auth/phone/verify",
            {"phone_number": "13800000000", "code": "１２３４５６"},
            "１２３４５６",
        ),
        (
            "/api/v1/auth/phone/resend-code",
            {"phone_number": "SyntheticInvalidPhoneMarker"},
            "SyntheticInvalidPhoneMarker",
        ),
    ],
)
def test_auth_validation_never_reflects_sensitive_input(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    marker: str,
) -> None:
    response = client.post(path, json=payload)

    _assert_safe_validation_response(response, marker)


@pytest.mark.parametrize("field", ["access_token", "refresh_token", "secret"])
def test_sensitive_extra_field_values_are_not_reflected(
    client: TestClient,
    field: str,
) -> None:
    marker = f"Synthetic{field.title()}Marker"
    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "validation-audit@example.com",
            "password": "SyntheticValid123",
            field: marker,
        },
    )

    _assert_safe_validation_response(response, marker)
    assert any(error["loc"][-1] == field for error in response.json()["detail"])


def test_nested_malformed_input_and_exception_context_are_not_reflected(
    client: TestClient,
) -> None:
    marker = "SyntheticNestedSecretMarker"
    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": {"secret": marker},
            "password": "SyntheticValid123",
        },
    )

    _assert_safe_validation_response(response, marker)


def test_missing_field_response_remains_useful(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"password": "SyntheticValid123"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "identifier"],
                "msg": "Field required.",
            }
        ]
    }


def test_validation_handler_does_not_log_request_body(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    marker = "SyntheticUnloggedPasswordMarker"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "validation-audit@example.com", "password": marker},
    )

    _assert_safe_validation_response(response, marker)
    assert marker not in caplog.text
