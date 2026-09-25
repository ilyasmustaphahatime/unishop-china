import pytest

from app.common.public_handles import (
    RESERVED_PUBLIC_HANDLES, generate_public_handle, normalize_public_handle,
)
from app.main import create_app
from app.core.config import settings


@pytest.mark.parametrize("value", ["abc", "a" * 30, "user-k7m4", "a_b", "a--b"])
def test_valid_handle_boundaries_and_normalization(value):
    assert normalize_public_handle(value) == value
    assert normalize_public_handle(value.upper()) == value


@pytest.mark.parametrize("value", [
    "", "a", "ab", "a" * 31, "a b", " abc", "abc ", "user/abc", "user\\abc",
    "a..b", ".", "..", "../admin", "%2Fadmin", "%252Fadmin", "a%20b", "a\x00b",
    "ab\n", "a\tb", "a\u202eb", "\U0001f600abc", "\u0430bc", "\u212aey", "a'b OR 1=1",
    "<script>", "javascript:", "a?b", "a#b", "-abc", "abc_",
    "550e8400-e29b-41d4-a716-446655440000",
])
def test_unsafe_handles_fail_without_echo(value):
    with pytest.raises(ValueError, match="^Invalid public handle.$"):
        normalize_public_handle(value)


@pytest.mark.parametrize("name", sorted(RESERVED_PUBLIC_HANDLES))
def test_reserved_names_rejected_case_insensitively(name):
    for value in (name, name.upper()):
        with pytest.raises(ValueError):
            normalize_public_handle(value)


def test_generation_is_public_random_and_has_no_identity_input():
    handles = {generate_public_handle() for _ in range(1000)}
    assert len(handles) == 1000
    assert all(len(h) == 25 and normalize_public_handle(h) == h for h in handles)


def test_all_openapi_variants_have_only_public_handle_path_parameters():
    config = settings.model_copy(update={
        "app_env": "development", "sms_enabled": True, "sms_provider": "fake",
        "enable_fake_sms_dev_inbox": True,
        "password_reset_delivery_provider": "fake", "enable_fake_password_reset_dev_inbox": True,
        "email_verification_delivery_provider": "fake", "enable_fake_email_verification_dev_inbox": True,
    })
    schema = create_app(config).openapi()
    operation_ids = []
    for path, item in schema["paths"].items():
        if path.startswith(("/api/v1/seller-verification", "/api/v1/admin/seller-verifications")):
            continue  # Phase 7 has separately tested private review/download contracts.
        for method, operation in item.items():
            if method not in {"get", "post", "patch", "delete", "put"}:
                continue
            operation_ids.append(operation["operationId"])
            for parameter in operation.get("parameters", []):
                assert parameter["in"] != "query"
                if parameter["in"] == "path":
                    assert parameter["name"] == "handle"
                    assert path == "/api/v1/profiles/by-handle/{handle}"
            assert not any(word in path for word in ("seller", "products", "chat", "admin"))
    assert len(operation_ids) == len(set(operation_ids)) == 27
    assert "/api/v1/profiles/{public_id}" not in schema["paths"]
    for kind in ("sms", "password-reset"):
        assert "post" in schema["paths"][f"/api/v1/dev/fake-{kind}/latest"]
    for kind in ("sms", "email", "password-reset"):
        assert "post" in schema["paths"][f"/api/v1/dev/fake-{kind}/consume"]


def test_authentication_secrets_are_body_fields_not_url_parameters():
    schema = create_app(settings).openapi()
    for path in ("/api/v1/auth/login", "/api/v1/auth/password/reset",
                 "/api/v1/auth/phone/verify", "/api/v1/auth/email/verify"):
        operation = schema["paths"][path]["post"]
        assert "application/json" in operation["requestBody"]["content"]
        assert not any(p["in"] in {"query", "path"} for p in operation.get("parameters", []))


@pytest.mark.parametrize("kind", ["sms", "email", "password-reset"])
def test_development_consumption_uses_body_and_preserves_access_controls(kind):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from app.api.v1.auth.dependencies import get_current_user

    class Store:
        def __init__(self):
            self.calls = []

        def consume_message(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    store = Store()
    config = settings.model_copy(update={
        "app_env": "development", "sms_enabled": True, "sms_provider": "fake",
        "enable_fake_sms_dev_inbox": True,
        "password_reset_delivery_provider": "fake", "enable_fake_password_reset_dev_inbox": True,
        "email_verification_delivery_provider": "fake", "enable_fake_email_verification_dev_inbox": True,
    })
    app = create_app(config, fake_sms_store=store, fake_password_reset_store=store,
                     fake_email_verification_store=store)
    path = f"/api/v1/dev/fake-{kind}/consume"
    if kind == "email":
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            assert client.post(path, json={"message_id": "synthetic-reference"}).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="synthetic-owner")
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.post(path, json={"message_id": "synthetic-reference"})
        assert response.status_code == 204
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert client.delete(f"/api/v1/dev/fake-{kind}/synthetic-reference").status_code == 404
        assert client.post(path, json={"message_id": "../secret"}).status_code == 422
    assert len(store.calls) == 1
    if kind == "email":
        assert store.calls[0][1]["user_id"] == "synthetic-owner"
    with TestClient(app, client=("203.0.113.10", 50000)) as client:
        assert client.post(path, json={"message_id": "synthetic-reference"},
                           headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 403
    assert len(store.calls) == 1
