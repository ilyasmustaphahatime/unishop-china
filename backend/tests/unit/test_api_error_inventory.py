"""Document existing safe runtime errors without changing HTTP contracts."""
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.errors import SafeErrorResponse


def test_all_registered_http_operations_have_a_safe_fallback_error_contract():
    spec = create_app().openapi()
    for methods in spec["paths"].values():
        for method, operation in methods.items():
            if method in {"get", "post", "patch", "put", "delete"}:
                schema = operation["responses"]["default"]["content"]["application/json"]["schema"]
                assert schema["$ref"].endswith("/SafeErrorResponse")
    schema = spec["paths"]["/api/v1/profile/me"]["patch"]["responses"]["422"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/SafeErrorResponse")


def test_unauthenticated_error_matches_documented_safe_contract():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/profile/me")
    assert response.status_code == 401
    assert SafeErrorResponse.model_validate(response.json()).detail


def test_database_outage_is_documented_with_its_existing_non_detail_shape(monkeypatch):
    app = create_app()
    monkeypatch.setattr("app.api.v1.router.check_database_connection", lambda: False)
    with TestClient(app) as client:
        response = client.get("/api/v1/health/database")
    assert response.status_code == 503
    assert response.json() == {"database": "mysql", "status": "unavailable", "connected": False}
    assert "503" in app.openapi()["paths"]["/api/v1/health/database"]["get"]["responses"]


def test_private_evidence_documents_binary_not_json_success():
    responses = create_app().openapi()["paths"]["/api/v1/seller-verification/evidence/content"]["get"]["responses"]
    assert set(responses["200"]["content"]) == {"image/jpeg", "image/png"}
    assert "application/json" not in responses["200"]["content"]
