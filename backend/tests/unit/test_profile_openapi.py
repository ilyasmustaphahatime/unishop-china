from app.main import app


def test_phase_6_profile_operations_are_unique_and_exact() -> None:
    schema = app.openapi()
    operations = {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method in ("get", "post", "patch", "put", "delete")
        if method in path_item
        and (path.startswith("/api/v1/profile/") or path.startswith("/api/v1/profiles/"))
    }

    assert operations == {
        ("GET", "/api/v1/profile/me"),
        ("PATCH", "/api/v1/profile/me"),
        ("POST", "/api/v1/profile/onboarding/complete"),
        ("GET", "/api/v1/profiles/{public_id}"),
    }


def test_profile_update_openapi_schema_is_a_strict_allow_list() -> None:
    request_schema = app.openapi()["components"]["schemas"]["ProfileUpdateRequest"]

    assert request_schema["additionalProperties"] is False
    assert set(request_schema["properties"]) == {"display_name", "bio", "city"}


def test_public_profile_openapi_schema_has_no_private_fields() -> None:
    public_schema = app.openapi()["components"]["schemas"]["PublicProfileResponse"]

    assert set(public_schema["properties"]) == {
        "public_id",
        "display_name",
        "bio",
        "city",
        "member_since",
        "email_verified",
        "phone_verified",
    }
    assert not {
        "id",
        "user_id",
        "email",
        "phone_number",
        "roles",
        "account_status",
    } & set(public_schema["properties"])
