"""Behavior and query budgets for the Phase 1-8 architecture stabilization."""
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.common.enums import UserRoleType
from app.models import User, UserRole, SellerVerification, SellerEvidence
from app.models.base import utc_now
from app.models.seller_verification import EvidenceType, VerificationStatus
from app.services.seller_verification_service import SellerVerificationService, VerificationError
from app.services.storage_service import LocalPrivateStorage


def make_verified_user(db, *, admin=False):
    user = User(email=f"architecture-{uuid4().hex}@example.test", password_hash="unusable",
                email_verified=True, phone_verified=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role=UserRoleType.ADMIN if admin else UserRoleType.BUYER))
    db.flush()
    return user


def submitted_request(db, user):
    row = SellerVerification(user_id=user.id, status=VerificationStatus.UNDER_REVIEW,
                             submitted_at=utc_now())
    db.add(row)
    db.flush()
    for kind in EvidenceType:
        db.add(SellerEvidence(verification_id=row.id, evidence_type=kind,
                              storage_key=uuid4().hex + uuid4().hex, file_hash="0" * 64,
                              mime_type="image/png", size=10))
    db.flush()
    return row


def test_admin_queue_batches_evidence_without_changing_private_contract(db_session, tmp_path):
    admin = make_verified_user(db_session, admin=True)
    rows = [submitted_request(db_session, make_verified_user(db_session)) for _ in range(4)]
    expected = {row.review_reference for row in rows}
    service = SellerVerificationService(LocalPrivateStorage(tmp_path / "private"))
    selects = []

    def count_evidence_queries(connection, cursor, statement, parameters, context, executemany):
        sql = " ".join(statement.lower().split())
        if sql.startswith("select") and "from seller_evidence" in sql:
            selects.append(sql)

    connection = db_session.connection()
    event.listen(connection, "before_cursor_execute", count_evidence_queries)
    try:
        result = service.list_pending(db_session, admin.id, 0)
    finally:
        event.remove(connection, "before_cursor_execute", count_evidence_queries)
    assert {row.review_reference for row in result} == expected
    assert all({item.evidence_type for item in row.evidence} == set(EvidenceType) for row in result)
    assert all(set(item.model_dump()) == {"evidence_type", "mime_type", "size"}
               for row in result for item in row.evidence)
    assert len(selects) == 1
    assert "for update" in selects[0]


@pytest.mark.parametrize("actor", ["owner", "admin", "other"])
def test_evidence_ticket_orchestration_stays_inside_authorized_service(db_session, tmp_path, actor):
    owner = make_verified_user(db_session)
    admin = make_verified_user(db_session, admin=True)
    other = make_verified_user(db_session)
    row = submitted_request(db_session, owner)
    reference = row.review_reference
    actor_id = {"owner": owner.id, "admin": admin.id, "other": other.id}[actor]
    db_session.commit()  # Preserve setup across a deliberately rolled-back denied operation.
    storage = LocalPrivateStorage(tmp_path / "private")
    service = SellerVerificationService(storage)
    if actor == "other":
        with pytest.raises(VerificationError) as error:
            service.issue_evidence_ticket(db_session, actor_id, reference, EvidenceType.SELFIE)
        assert error.value.status == 404
        assert not storage.tickets
    else:
        ticket = service.issue_evidence_ticket(db_session, actor_id, reference, EvidenceType.SELFIE)
        key, ticket_reference, kind = storage.redeem(ticket, actor_id)
        assert ticket_reference == reference and kind == "SELFIE"
        assert key not in ticket
