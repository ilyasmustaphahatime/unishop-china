"""Browsers need readable challenge/backoff headers, not private cookie headers."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import allowed_frontend_origins, settings
from app.main import create_app


@pytest.mark.parametrize("allowed", [True, False])
def test_browser_can_read_bearer_challenge_only_from_allowed_origin(allowed):
    origin = next(iter(allowed_frontend_origins(settings))) if allowed else "https://untrusted.invalid"
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/auth/me", headers={"Origin": origin})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
        exposed = {value.strip().lower() for value in response.headers["access-control-expose-headers"].split(",")}
        assert exposed == {"www-authenticate", "retry-after"}
    else:
        assert "access-control-allow-origin" not in response.headers
