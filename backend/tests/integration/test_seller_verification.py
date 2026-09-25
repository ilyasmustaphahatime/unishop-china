"""Real MySQL API, ownership, upload and rollback regressions for Phase 7."""
from io import BytesIO
from uuid import uuid4
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from app.core.config import settings
from app.core.database import get_db
from app.main import create_app
from app.models import User, UserRole, SellerVerification, SellerEvidence, SellerVerificationAudit
from app.common.enums import UserRoleType, AccountStatus
from app.models.seller_verification import EvidenceType
from app.services.storage_service import LocalPrivateStorage
from app.services.seller_verification_service import SellerVerificationService
from app.services.token_service import AccessTokenService
from app.api.v1.seller_verification.dependencies import get_seller_service, limiters

BASE = "/api/v1/seller-verification"
ADMIN = "/api/v1/admin/seller-verifications"


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (16, 16), "blue").save(stream, "PNG")
    return stream.getvalue()


def make_user(db, *, admin=False):
    user = User(email=f"seller-test-{uuid4().hex}@example.test", password_hash="unusable",
                email_verified=True, phone_verified=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role=UserRoleType.ADMIN if admin else UserRoleType.BUYER))
    db.flush()
    return user


@pytest.fixture
def setup(db_session, tmp_path):
    for pair in limiters.values():
        for limiter in pair:
            limiter.clear()
    user, other, admin = make_user(db_session), make_user(db_session), make_user(db_session, admin=True)
    storage = LocalPrivateStorage(tmp_path / "private")
    service = SellerVerificationService(storage)
    app = create_app(settings.model_copy(update={"app_debug": False}))
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_seller_service] = lambda: service
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_session, user, other, admin, service


def headers(user):
    return {"Authorization": "Bearer " + AccessTokenService().create_access_token(user.id)}


def start(client, user):
    response = client.post(BASE, json={"action": "start"}, headers=headers(user))
    assert response.status_code == 200
    return response.json()


def upload(client, user, kind="SELFIE", **kwargs):
    return client.post(BASE + "/evidence", headers=headers(user),
                       data={"evidence_type": kind}, files={"file": kwargs.get("file", ("proof.png", image_bytes(), "image/png"))})


def submitted(client, user):
    result = start(client, user)
    for kind in EvidenceType:
        assert upload(client, user, kind.value).status_code == 200
    response = client.post(BASE, json={"action": "submit"}, headers=headers(user))
    assert response.status_code == 200
    assert response.json()["status"] == "UNDER_REVIEW"
    return result["review_reference"]


def test_full_workflow_and_private_contract(setup):
    client, db, user, other, admin, service = setup
    assert client.get(BASE + "/me", headers=headers(user)).json() is None
    ref = submitted(client, user)
    assert upload(client, user).status_code == 409
    assert client.post(BASE, json={"action": "start"}, headers=headers(user)).status_code == 409
    response = client.get(ADMIN, headers=headers(admin))
    assert response.status_code == 200 and response.json()[0]["review_reference"] == ref
    body = response.json()[0]
    assert {"id", "user_id", "reviewed_by", "storage_key", "file_hash", "url"}.isdisjoint(body)
    assert set(body["evidence"][0]) == {"evidence_type", "size", "mime_type"}
    response = client.post(f"{ADMIN}/{ref}/approve", json={}, headers=headers(admin))
    assert response.status_code == 200 and response.json()["status"] == "VERIFIED"
    assert client.post(f"{ADMIN}/{ref}/reject", json={"rejection_reason": "Different choice"}, headers=headers(admin)).status_code == 409
    assert client.get(BASE + "/me", headers=headers(other)).json() is None
    assert db.scalar(select(func.count()).select_from(SellerVerificationAudit)) == 6
    assert db.scalar(select(UserRole).where(UserRole.user_id == user.id)).role == UserRoleType.BUYER


def test_rejected_attempt_can_restart_without_reusing_evidence(setup):
    client, db, user, other, admin, service = setup
    ref = submitted(client, user)
    response = client.post(f"{ADMIN}/{ref}/reject", json={"rejection_reason": "Image is unclear"}, headers=headers(admin))
    assert response.status_code == 200
    next_attempt = start(client, user)
    assert next_attempt["review_reference"] != ref
    assert next_attempt["evidence"] == []
    assert client.post(BASE, json={"action": "submit"}, headers=headers(user)).status_code == 409


@pytest.mark.parametrize("field,value", [("user_id", "other"), ("status", "VERIFIED"), ("reviewed_by", "admin")])
def test_mass_assignment_rejected(setup, field, value):
    client, _, user, *_ = setup
    response = client.post(BASE, json={"action": "start", field: value}, headers=headers(user))
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["email_verified", "phone_verified"])
def test_unverified_users_cannot_start(setup, field):
    client, db, user, *_ = setup
    setattr(user, field, False)
    db.flush()
    assert client.post(BASE, json={"action": "start"}, headers=headers(user)).status_code == 403


def test_inactive_account_rejected(setup):
    client, db, user, *_ = setup
    token_headers = headers(user)
    user.account_status = AccountStatus.SUSPENDED
    db.flush()
    assert client.post(BASE, json={"action": "start"}, headers=token_headers).status_code == 401


def test_admin_authorization_idor_and_signed_access(setup):
    client, db, user, other, admin, service = setup
    ref = submitted(client, user)
    assert client.get(ADMIN, headers=headers(other)).status_code == 403
    assert client.post(f"{ADMIN}/{ref}/approve", json={}, headers=headers(other)).status_code == 403
    body = {"review_reference": ref, "evidence_type": "SELFIE"}
    assert client.post(BASE + "/evidence/access", json=body, headers=headers(other)).status_code == 404
    response = client.post(BASE + "/evidence/access", json=body, headers=headers(user))
    url = response.json()["url"]
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(other)).status_code == 422
    downloaded = client.get(url, headers=headers(user))
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["referrer-policy"] == "no-referrer"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert downloaded.headers["content-disposition"].startswith("attachment")
    assert client.get(url, headers=headers(user)).status_code == 422
    assert service.storage.read(next(iter(service.storage.root.iterdir())).name)


def test_admin_cannot_self_review(setup):
    client, _, _, _, admin, _ = setup
    ref = submitted(client, admin)
    assert client.post(f"{ADMIN}/{ref}/approve", json={}, headers=headers(admin)).status_code == 403


@pytest.mark.parametrize("file", [
    ("payload.exe", b"MZ payload", "application/octet-stream"),
    ("proof.png", b"not a PNG", "image/png"),
    ("proof.jpg", image_bytes(), "image/jpeg"),
    ("../proof.png", image_bytes(), "image/png"),
    ("proof.php.png", image_bytes(), "image/png"),
    ("proof.png", image_bytes(), "text/html"),
    ("proof.png", b"x" * (5 * 1024 * 1024 + 1), "image/png"),
])
def test_malicious_uploads_rejected_without_storage(setup, file):
    client, _, user, _, _, service = setup
    start(client, user)
    response = upload(client, user, file=file)
    assert response.status_code == 422
    assert not service.storage.root.exists()


def test_extra_multipart_owner_rejected(setup):
    client, _, user, other, _, _ = setup
    start(client, user)
    response = client.post(BASE + "/evidence", headers=headers(user),
                           data={"evidence_type": "SELFIE", "user_id": other.id},
                           files={"file": ("proof.png", image_bytes(), "image/png")})
    assert response.status_code == 422


def test_model_unique_active_request_and_evidence_slot(setup):
    client, db, user, *_ = setup
    start(client, user)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(SellerVerification(user_id=user.id))
        db.flush()


def test_upload_rolls_back_database_and_private_file_on_failure(setup, monkeypatch):
    client, db, user, _, _, service = setup
    start(client, user)
    baseline = db.scalar(select(func.count()).select_from(SellerEvidence))
    def fail(*args):
        raise RuntimeError("controlled audit failure")
    monkeypatch.setattr(service, "audit", fail)
    response = upload(client, user)
    assert response.status_code == 503
    assert db.scalar(select(func.count()).select_from(SellerEvidence)) == baseline
    assert list(service.storage.root.iterdir()) == []


def test_review_rechecks_admin_role_and_owner_eligibility(setup):
    client, db, user, other, admin, service = setup
    ref = submitted(client, user)
    user.email_verified = False
    db.flush()
    assert client.post(f"{ADMIN}/{ref}/approve", json={}, headers=headers(admin)).status_code == 403
    assert client.get(BASE + "/me", headers=headers(user)).json()["status"] == "UNDER_REVIEW"


def test_limits_cache_headers_and_incomplete_transition(setup):
    client, db, user, *_ = setup
    start(client, user)
    for _ in range(4):
        assert client.post(BASE, json={"action": "submit"}, headers=headers(user)).status_code == 409
    response = client.post(BASE, json={"action": "submit"}, headers=headers(user))
    assert response.status_code == 429 and "retry-after" in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_oversized_ingress_rejected_before_parsing(setup):
    client, _, user, *_ = setup
    response = client.post(BASE + "/evidence", headers={**headers(user), "Content-Length": "99999999"}, content=b"")
    assert response.status_code == 413

def test_replaced_evidence_invalidates_issued_download(setup):
    client, _, user, _, _, _ = setup
    ref = start(client, user)["review_reference"]
    assert upload(client, user).status_code == 200
    access = client.post(BASE + "/evidence/access", json={
        "review_reference": ref, "evidence_type": "SELFIE"}, headers=headers(user))
    assert access.status_code == 200
    assert upload(client, user).status_code == 200
    assert client.get(access.json()["url"], headers=headers(user)).status_code == 404


def test_review_transaction_rolls_back_on_audit_failure(setup, monkeypatch):
    client, db, user, _, admin, service = setup
    ref = submitted(client, user)
    def fail(*args):
        raise RuntimeError("controlled failure")
    monkeypatch.setattr(service, "audit", fail)
    assert client.post(f"{ADMIN}/{ref}/approve", json={}, headers=headers(admin)).status_code == 503
    current = client.get(BASE + "/me", headers=headers(user)).json()
    assert current["status"] == "UNDER_REVIEW" and current["reviewed_at"] is None


def test_duplicate_evidence_type_is_rejected_by_database(setup):
    client, db, user, _, _, _ = setup
    start(client, user)
    upload(client, user)
    existing = db.scalar(select(SellerEvidence))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(SellerEvidence(verification_id=existing.verification_id, evidence_type=existing.evidence_type,
                              storage_key="f" * 64, file_hash="e" * 64, mime_type="image/png", size=1))
        db.flush()


def test_invalid_terminal_state_without_review_dates_is_rejected(setup):
    _, db, _, other, _, _ = setup
    with pytest.raises(OperationalError) as error, db.begin_nested():
        db.add(SellerVerification(user_id=other.id, status="VERIFIED"))
        db.flush()
    assert error.value.orig.args[0] == 3819


def test_revoked_admin_cannot_redeem_existing_evidence_grant(setup):
    client, db, user, _, admin, _ = setup
    ref = submitted(client, user)
    granted = client.post(BASE + "/evidence/access", json={
        "review_reference": ref, "evidence_type": "SELFIE"}, headers=headers(admin))
    assert granted.status_code == 200
    role = db.scalar(select(UserRole).where(UserRole.user_id == admin.id, UserRole.role == UserRoleType.ADMIN))
    db.delete(role)
    db.flush()
    assert client.get(granted.json()["url"], headers=headers(admin)).status_code == 404


def test_lowercase_bearer_upload_and_missing_auth(setup):
    client, _, user, _, _, _ = setup
    start(client, user)
    auth = headers(user)["Authorization"].replace("Bearer ", "bearer ")
    response = client.post(BASE + "/evidence", headers={"Authorization": auth},
                           data={"evidence_type": "SELFIE"},
                           files={"file": ("proof.png", image_bytes(), "image/png")})
    assert response.status_code == 200
    assert client.post(BASE, json={"action": "start"}).status_code == 401


def test_admin_review_rejects_mass_assignment_and_unsafe_reason(setup):
    client, _, user, _, admin, _ = setup
    ref = submitted(client, user)
    for payload in ({"status": "VERIFIED"}, {"reviewed_by": admin.id}):
        assert client.post(f"{ADMIN}/{ref}/approve", json=payload, headers=headers(admin)).status_code == 422
    for reason in ("  ", "x" * 501, "bad\u202ereason"):
        response = client.post(f"{ADMIN}/{ref}/reject", json={"rejection_reason": reason}, headers=headers(admin))
        assert response.status_code == 422


def test_phase7_openapi_contract_has_only_deliberate_private_parameters(setup):
    client, *_ = setup
    schema = client.app.openapi()
    operations = [(path, method, op) for path, item in schema["paths"].items()
                  for method, op in item.items() if method in {"get", "post", "put", "patch", "delete"}]
    ids = [op["operationId"] for _, _, op in operations]
    assert len(ids) == len(set(ids))
    seller = [(path, method, op) for path, method, op in operations if "seller-verification" in path]
    assert len(seller) == 8
    for path, _, op in seller:
        for parameter in op.get("parameters", []):
            assert parameter["name"] in {"id", "offset", "ticket"}
            if parameter["name"] == "ticket":
                assert path == BASE + "/evidence/content"
    assert "multipart/form-data" in schema["paths"][BASE + "/evidence"]["post"]["requestBody"]["content"]


def test_storage_fails_closed_outside_development(setup):
    client, _, user, *_ = setup
    from app.api.v1.seller_verification.dependencies import get_seller_service
    client.app.dependency_overrides.pop(get_seller_service)
    original = client.app.state.settings
    client.app.state.settings = original.model_copy(update={"app_env": "production"})
    try:
        assert client.get(BASE + "/me", headers=headers(user)).status_code == 503
    finally:
        client.app.state.settings = original


def test_storage_rejects_web_served_directory_even_through_parent_segments(setup):
    client, _, user, *_ = setup
    from app.api.v1.seller_verification.dependencies import get_seller_service
    from app.core.config import BACKEND_DIR
    client.app.dependency_overrides.pop(get_seller_service)
    client.app.state.settings = client.app.state.settings.model_copy(update={
        "seller_private_storage_dir": BACKEND_DIR / "private_uploads" / ".." / ".." / "frontend" / "public",
    })
    assert client.get(BASE + "/me", headers=headers(user)).status_code == 503
