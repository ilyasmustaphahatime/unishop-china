"""Private download URL, authorization and transactional audit regressions."""
import pytest
from sqlalchemy import select, func

from app.common.enums import AccountStatus
from app.core.config import allowed_frontend_origins
from app.models import SellerVerificationAudit, SellerVerification, SellerEvidence
from tests.integration.test_seller_verification import (
    ADMIN, BASE, headers, setup as setup, submitted, start, upload,
)


def grant(client, actor, reference):
    response = client.post(BASE + "/evidence/access", headers=headers(actor), json={
        "review_reference": reference, "evidence_type": "SELFIE",
    })
    assert response.status_code == 200
    return response.json()


def download(client, actor, access):
    return client.get(access["url"], headers={
        **headers(actor), "X-Evidence-Ticket": access["ticket"],
    })


def test_download_credential_is_never_part_of_url(setup):
    client, _, owner, _, admin, _ = setup
    access = grant(client, admin, submitted(client, owner))
    assert access["url"] == BASE + "/evidence/content"
    assert len(access["ticket"]) == 129
    assert access["expires_in"] == 60


def test_successful_admin_evidence_read_has_authoritative_audit(setup):
    client, db, owner, _, admin, _ = setup
    access = grant(client, admin, submitted(client, owner))
    assert download(client, admin, access).status_code == 200
    event = db.scalar(select(SellerVerificationAudit).where(
        SellerVerificationAudit.event == "EVIDENCE_READ"))
    assert event is not None
    assert event.actor_id == admin.id and event.created_at is not None


@pytest.mark.parametrize("failure", ["audit", "commit", "storage", "digest"])
def test_failed_private_read_never_releases_bytes_or_success_audit(setup, monkeypatch, failure):
    client, db, owner, _, admin, service = setup
    access = grant(client, admin, submitted(client, owner))

    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic-private-detail-must-not-escape")

    if failure == "audit":
        original = service.audit
        def fail_after_insert(*args):
            original(*args)
            db.flush()
            fail()
        monkeypatch.setattr(service, "audit", fail_after_insert)
    elif failure == "commit":
        monkeypatch.setattr(db, "commit", fail)
    elif failure == "storage":
        monkeypatch.setattr(service.storage, "read", fail)
    else:
        monkeypatch.setattr(service.storage, "read", lambda _key: b"corrupt synthetic bytes")
    response = download(client, admin, access)
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/json"
    assert "synthetic" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(SellerVerificationAudit).where(
        SellerVerificationAudit.event == "EVIDENCE_READ")) == 0


def test_query_ticket_is_not_accepted_and_errors_do_not_reflect_it(setup):
    client, _, owner, _, admin, _ = setup
    access = grant(client, admin, submitted(client, owner))
    # Legacy query transport is deliberately not accepted; a header is mandatory.
    response = client.get(access["url"], params={"ticket": access["ticket"]}, headers=headers(admin))
    assert response.status_code == 422
    assert access["ticket"] not in response.text
    assert download(client, admin, access).status_code == 200


def test_download_header_cors_is_limited_to_trusted_origin(setup):
    client, *_ = setup
    origin = next(iter(allowed_frontend_origins(client.app.state.settings)))
    preflight = {"Origin": origin, "Access-Control-Request-Method": "GET",
                 "Access-Control-Request-Headers": "authorization,x-evidence-ticket"}
    response = client.options(BASE + "/evidence/content", headers=preflight)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    preflight["Origin"] = "https://attacker.example"
    response = client.options(BASE + "/evidence/content", headers=preflight)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("status", list(AccountStatus))
def test_current_account_state_controls_every_seller_operation(setup, status):
    client, db, owner, _, admin, _ = setup
    reference = start(client, owner)["review_reference"]
    for kind in ("SELFIE", "WECHAT_PROOF", "HANDWRITTEN_CODE"):
        assert upload(client, owner, kind).status_code == 200
    access = grant(client, owner, reference)
    auth = headers(owner)
    owner.account_status = status
    db.flush()
    active = status == AccountStatus.ACTIVE
    assert client.get(BASE + "/me", headers=auth).status_code == (200 if active else 401)
    assert download(client, owner, access).status_code == (200 if active else 401)
    assert upload(client, owner).status_code == (200 if active else 401)
    assert client.post(BASE, json={"action": "start"}, headers=auth).status_code == (409 if active else 401)
    assert client.post(BASE + "/evidence/access", json={
        "review_reference": reference, "evidence_type": "SELFIE",
    }, headers=auth).status_code == (200 if active else 401)
    assert client.post(BASE, json={"action": "submit"}, headers=auth).status_code == (200 if active else 401)
    # Admin authority comes from current DB state, not a token issued when active.
    admin.account_status = status
    db.flush()
    assert client.get(ADMIN, headers=headers(admin)).status_code == (200 if active else 401)
    assert client.post(f"{ADMIN}/{reference}/approve", json={}, headers=headers(admin)).status_code == (
        200 if active else 401)
    assert client.post(f"{ADMIN}/{reference}/reject", json={"rejection_reason": "Image unclear"},
                       headers=headers(admin)).status_code == (409 if active else 401)


def test_schema_invalid_requests_consume_budget_and_forwarded_peer_does_not_bypass(setup):
    client, _, owner, *_ = setup
    for _ in range(5):
        assert client.post(BASE, json={}, headers=headers(owner)).status_code == 422
    response = client.post(BASE, json={}, headers={
        **headers(owner), "X-Forwarded-For": "203.0.113.123", "Forwarded": "for=203.0.113.123",
    })
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.parametrize("path,budget", [(BASE, 15), (ADMIN + "/" + "f" * 32 + "/approve", 90)])
def test_invalid_json_cannot_bypass_seller_peer_limit(setup, path, budget):
    client, _, _, _, admin, _ = setup
    for _ in range(budget):
        assert client.post(path, content=b"{", headers={
            **headers(admin), "Content-Type": "application/json",
        }).status_code == 422
    response = client.post(path, content=b"{", headers={
        **headers(admin), "Content-Type": "application/json", "X-Forwarded-For": "203.0.113.7",
    })
    assert response.status_code == 429
    assert response.headers["cache-control"] == "no-store"
    assert int(response.headers["retry-after"]) > 0


def test_storage_write_failure_preserves_draft_and_existing_evidence(setup, monkeypatch):
    client, db, owner, _, _, service = setup
    reference = start(client, owner)["review_reference"]
    assert upload(client, owner).status_code == 200
    row = db.scalar(select(SellerEvidence).join(SellerVerification).where(
        SellerVerification.review_reference == reference))
    original_key, original_hash = row.storage_key, row.file_hash
    original_bytes = service.storage.read(original_key)
    count = db.scalar(select(func.count()).select_from(SellerVerificationAudit))
    def fail(_data):
        raise OSError("synthetic private path")
    monkeypatch.setattr(service.storage, "upload", fail)
    assert upload(client, owner).status_code == 503
    db.refresh(row)
    assert (row.storage_key, row.file_hash) == (original_key, original_hash)
    assert service.storage.read(original_key) == original_bytes
    assert db.scalar(select(func.count()).select_from(SellerVerificationAudit)) == count
