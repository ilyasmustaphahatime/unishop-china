from app.main import create_app
from app.schemas.errors import SafeErrorResponse


def test_all_personalization_operations_document_safe_runtime_errors():
    spec = create_app().openapi()
    operations = [operation for path, methods in spec["paths"].items()
                  if path.startswith(("/api/v1/me/favorites", "/api/v1/me/recently-viewed"))
                  for method, operation in methods.items()
                  if method in {"get", "post", "put", "delete"}]
    assert len(operations) == 8
    for operation in operations:
        assert operation["security"]
        for status in (400, 401, 404, 408, 409, 413, 415, 422, 429, 500, 503):
            assert operation["responses"][str(status)]["content"]["application/json"]["schema"]["$ref"].endswith("/SafeErrorResponse")


def test_documented_errors_accept_both_transport_and_validation_shapes():
    for detail in ("Invalid cursor.", [{"loc": ["body", "product_slugs"],
                                       "type": "missing", "msg": "Field required."}]):
        assert SafeErrorResponse.model_validate({"detail": detail})
