"""Expiring handwritten challenges and a DB-authoritative public boolean only."""
from datetime import timedelta

import pytest
from sqlalchemy import select, func

from app.common.datetime_utils import as_utc
from app.common.enums import AccountStatus
from app.models import SellerVerification, SellerEvidence, SellerVerificationAudit, UserProfile
from app.models.base import utc_now
from app.models.seller_verification import EvidenceType, VerificationStatus
from tests.integration.test_seller_verification import (
    ADMIN, BASE, headers, image_bytes, setup as setup, start, submitted, upload,
)


def fill_draft(client, owner):
    draft = start(client, owner)
    for kind in EvidenceType:
        assert upload(client, owner, kind.value).status_code == 200
    return draft


@pytest.mark.parametrize("boundary", [0, 1])
def test_expired_challenge_blocks_submission_and_handwritten_upload(setup, monkeypatch, boundary):
    client, db, owner, _, _, service = setup
    draft = fill_draft(client, owner)
    row = db.scalar(select(SellerVerification).where(SellerVerification.review_reference == draft["review_reference"]))
    monkeypatch.setattr(service, "now", lambda: as_utc(row.challenge_expires_at) + timedelta(seconds=boundary))
    assert client.post(BASE, json={"action": "submit"}, headers=headers(owner)).status_code == 409
    assert upload(client, owner, "HANDWRITTEN_CODE").status_code == 409
    db.refresh(row)
    assert row.status == VerificationStatus.PENDING and row.submitted_at is None


def test_renewal_requires_new_handwritten_evidence_and_invalidates_stale_upload(setup):
    client, db, owner, _, _, service = setup
    original = fill_draft(client, owner)
    row = db.scalar(select(SellerVerification).where(SellerVerification.review_reference == original["review_reference"]))
    evidence = db.scalar(select(SellerEvidence).where(
        SellerEvidence.verification_id == row.id, SellerEvidence.evidence_type == EvidenceType.HANDWRITTEN_CODE))
    old_key = evidence.storage_key
    response = client.post(BASE, json={"action": "renew_challenge"}, headers=headers(owner))
    assert response.status_code == 200
    renewed = response.json()
    assert renewed["handwritten_challenge"] != original["handwritten_challenge"]
    assert {e["evidence_type"] for e in renewed["evidence"]} == {"SELFIE", "WECHAT_PROOF"}
    assert not (service.storage.root / old_key).exists()
    assert client.post(BASE, json={"action": "submit"}, headers=headers(owner)).status_code == 409
    stale = client.post(BASE + "/evidence", headers=headers(owner), data={
        "evidence_type": "HANDWRITTEN_CODE", "challenge": original["handwritten_challenge"],
    }, files={"file": ("proof.png", image_bytes(), "image/png")})
    assert stale.status_code == 409
    assert upload(client, owner, "HANDWRITTEN_CODE").status_code == 200
    assert client.post(BASE, json={"action": "submit"}, headers=headers(owner)).status_code == 200
    assert db.scalar(select(func.count()).select_from(SellerVerificationAudit).where(
        SellerVerificationAudit.event == "CHALLENGE_RENEWED")) == 1


def test_failed_renewal_preserves_original_challenge_and_private_file(setup, monkeypatch):
    client, db, owner, _, _, service = setup
    original = fill_draft(client, owner)
    files = set(service.storage.root.iterdir())
    def fail(*_args):
        raise RuntimeError("synthetic failure")
    monkeypatch.setattr(service, "audit", fail)
    assert client.post(BASE, json={"action": "renew_challenge"}, headers=headers(owner)).status_code == 503
    current = client.get(BASE + "/me", headers=headers(owner)).json()
    assert current["handwritten_challenge"] == original["handwritten_challenge"]
    assert len(current["evidence"]) == 3
    assert set(service.storage.root.iterdir()) == files


@pytest.mark.parametrize("final_status", ["UNDER_REVIEW", "VERIFIED", "REJECTED"])
def test_submitted_challenge_cannot_be_renewed_even_after_expiry(setup, monkeypatch, final_status):
    client, db, owner, _, admin, service = setup
    reference = submitted(client, owner)
    monkeypatch.setattr(service, "now", lambda: utc_now() + timedelta(days=1))
    if final_status != "UNDER_REVIEW":
        action = "approve" if final_status == "VERIFIED" else "reject"
        payload = {} if action == "approve" else {"rejection_reason": "Code image unclear"}
        assert client.post(f"{ADMIN}/{reference}/{action}", headers=headers(admin), json=payload).status_code == 200
    assert client.post(BASE, json={"action": "renew_challenge"}, headers=headers(owner)).status_code == 409
    assert client.get(BASE + "/me", headers=headers(owner)).json()["status"] == final_status


@pytest.mark.parametrize("status", [None, *list(VerificationStatus)])
def test_public_profile_has_only_boolean_seller_indicator(setup, status):
    client, db, owner, _, admin, _ = setup
    profile = UserProfile(user_id=owner.id, display_name="Synthetic Public Seller", city="Qingdao",
                          onboarding_completed=True)
    db.add(profile)
    db.flush()
    path = "/api/v1/profiles/by-handle/" + profile.public_handle
    if status == VerificationStatus.PENDING:
        start(client, owner)
    elif status:
        reference = submitted(client, owner)
        if status in (VerificationStatus.VERIFIED, VerificationStatus.REJECTED):
            action = "approve" if status == VerificationStatus.VERIFIED else "reject"
            payload = {} if action == "approve" else {"rejection_reason": "Code image unclear"}
            assert client.post(f"{ADMIN}/{reference}/{action}", headers=headers(admin), json=payload).status_code == 200
    response = client.get(path)
    assert response.status_code == 200
    assert set(response.json()) == {"public_handle", "display_name", "bio", "city", "member_since",
                                    "email_verified", "phone_verified", "seller_verified"}
    assert response.json()["seller_verified"] is (status == VerificationStatus.VERIFIED)
    owner.account_status = AccountStatus.SUSPENDED
    db.flush()
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("challenge", [None, "invalid", "Ａ" * 12])
def test_handwritten_upload_requires_a_strict_body_challenge(setup, challenge):
    client, _, owner, *_ = setup
    start(client, owner)
    body = {"evidence_type": "HANDWRITTEN_CODE"}
    if challenge is not None:
        body["challenge"] = challenge
    response = client.post(BASE + "/evidence", headers=headers(owner), data=body,
                           files={"file": ("proof.png", image_bytes(), "image/png")})
    assert response.status_code == 422
