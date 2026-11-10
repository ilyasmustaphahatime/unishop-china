"""Pre-parser limits do not require a database or consume password hashing work."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.core.auth_request_security import AuthRequestBoundary, auth_request_rate_limiter
from app.core.database import get_db
from app.main import create_app


@pytest.mark.parametrize("path", [
    "login", "register", "password/forgot", "password/reset", "password/change",
    "phone/verify", "phone/resend-code", "email/verify", "email/resend-code",
    "refresh", "logout", "logout-all",
])
def test_malformed_auth_json_is_bounded_rate_limited_and_private(path, monkeypatch, caplog):
    monkeypatch.setattr(auth_request_rate_limiter, "max_requests", 2)
    app = create_app()
    def no_database():
        pytest.fail("Malformed auth JSON must not reach database dependencies.")
    app.dependency_overrides[get_db] = no_database
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post("/api/v1/auth/" + path, content=b'{"password":"SecretMarker",',
                                   headers={"Content-Type": "application/json"})
            assert response.status_code == 422
            assert "SecretMarker" not in response.text
        response = client.post("/api/v1/auth/" + path, content=b"{")
        assert response.status_code == 429
        assert response.headers["retry-after"]
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["pragma"] == "no-cache"
    assert "SecretMarker" not in caplog.text


@pytest.mark.parametrize("body", [
    b'{"password":"a","password":"b"}', b'{"nested":{"key":1,"key":2}}',
    b'{"password":NaN}', b'{"password":Infinity}', b'\xff', b'[' * 2000,
])
def test_ambiguous_or_invalid_auth_json_rejected(body):
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/auth/login", content=body,
                               headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def run_boundary(chunks, *, headers=(), method="POST", path="/api/v1/auth/login"):
    called, output = [], []
    async def downstream(scope, receive, send):
        called.append(await receive())
    iterator = iter(chunks)
    async def receive():
        return next(iterator)
    async def send(message):
        output.append(message)
    scope = dict(type="http", path=path, method=method, headers=list(headers), client=("192.0.2.4", 1))
    asyncio.run(AuthRequestBoundary(downstream, "/api/v1")(scope, receive, send))
    return called, output


def test_actual_chunked_bytes_not_content_length_control_bound():
    called, output = run_boundary([
        {"type": "http.request", "body": b"x" * 10000, "more_body": True},
        {"type": "http.request", "body": b"x" * 10000, "more_body": False},
    ], headers=[(b"content-length", b"1")])
    assert not called and output[0]["status"] == 413


def test_timeout_fails_closed(monkeypatch):
    async def timeout(*args, **kwargs):
        raise TimeoutError
    monkeypatch.setattr("app.core.auth_request_security.bounded_json_body", timeout)
    called, output = run_boundary([])
    assert not called and output[0]["status"] == 408


def test_disconnect_does_not_continue_processing():
    called, output = run_boundary([{"type": "http.disconnect"}])
    assert not called and not output


@pytest.mark.parametrize("content_type", [b"application/json", b"application/problem+json"])
def test_valid_body_replayed_unchanged(content_type):
    body = json.dumps({"password": "SyntheticValue"}).encode()
    called, output = run_boundary([{"type": "http.request", "body": body}],
                                  headers=[(b"content-type", content_type)])
    assert not output and called == [{"type": "http.request", "body": body, "more_body": False}]


def test_schema_invalid_requests_also_consume_preparser_budget(monkeypatch):
    monkeypatch.setattr(auth_request_rate_limiter, "max_requests", 1)
    with TestClient(create_app()) as client:
        assert client.post("/api/v1/auth/login", json={}).status_code == 422
        assert client.post("/api/v1/auth/login", json={}).status_code == 429


def test_auth_transport_errors_are_documented():
    spec = create_app().openapi()
    operations = [operation for path, methods in spec["paths"].items()
                  if path.startswith("/api/v1/auth/")
                  for method, operation in methods.items() if method in {"get", "post"}]
    assert operations
    for operation in operations:
        for status in (408, 413, 415, 422, 429):
            response = operation["responses"][str(status)]
            assert response["content"]["application/json"]["schema"]["$ref"].endswith("/SafeErrorResponse")
