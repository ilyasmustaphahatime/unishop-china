from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session
from app.core.database import engine
from app.models import User, UserRole, SellerVerification, SellerEvidence, SellerVerificationAudit
from app.common.enums import UserRoleType
from app.models.seller_verification import EvidenceType
from app.services.seller_verification_service import SellerVerificationService, VerificationError
from app.services.storage_service import LocalPrivateStorage, sanitize_image
from tests.integration.test_seller_verification import image_bytes


@pytest.fixture
def world(tmp_path):
    ids = []
    with Session(engine) as db, db.begin():
        for role in (UserRoleType.BUYER, UserRoleType.ADMIN):
            user = User(email=f"seller-race-{uuid4().hex}@example.test", password_hash="unusable",
                        email_verified=True, phone_verified=True)
            db.add(user)
            db.flush()
            ids.append(user.id)
            db.add(UserRole(user_id=user.id, role=role))
    yield SellerVerificationService(LocalPrivateStorage(tmp_path)), ids[0], ids[1]
    with Session(engine) as db, db.begin():
        db.execute(delete(User).where(User.id.in_(ids)))


def call(operation):
    with Session(engine) as db:
        try:
            return operation(db)
        except VerificationError as error:
            return error.status


def race(first, second):
    barrier = Barrier(2)
    def run(operation):
        barrier.wait(timeout=10)
        return call(operation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, first), pool.submit(run, second)]
        return [future.result(timeout=20) for future in futures]


def ready(service, owner):
    call(lambda db: service.start_or_submit(db, owner, "start"))
    image = sanitize_image(image_bytes(), "proof.png", "image/png")
    for kind in EvidenceType:
        call(lambda db: service.upload(db, owner, kind, image))
    return call(lambda db: service.start_or_submit(db, owner, "submit"))


def test_concurrent_start_has_one_active_verification(world):
    service, owner, _ = world
    outcomes = race(lambda db: service.start_or_submit(db, owner, "start"),
                    lambda db: service.start_or_submit(db, owner, "start"))
    assert outcomes.count(409) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(SellerVerification).where(
            SellerVerification.user_id == owner)) == 1


def test_concurrent_approve_reject_has_one_terminal_decision(world):
    service, owner, admin = world
    ref = ready(service, owner).review_reference
    outcomes = race(lambda db: service.review(db, admin, ref, None),
                    lambda db: service.review(db, admin, ref, "Image unclear"))
    assert outcomes.count(409) == 1
    with Session(engine) as db:
        count = db.scalar(select(func.count()).select_from(SellerVerificationAudit).join(
            SellerVerification, SellerVerification.id == SellerVerificationAudit.verification_id).where(
                SellerVerification.user_id == owner,
                SellerVerificationAudit.event.in_(["APPROVAL", "REJECTION"])))
        assert count == 1


def test_concurrent_upload_replacement_keeps_one_row_and_file(world):
    service, owner, _ = world
    call(lambda db: service.start_or_submit(db, owner, "start"))
    image = sanitize_image(image_bytes(), "proof.png", "image/png")
    outcomes = race(lambda db: service.upload(db, owner, EvidenceType.SELFIE, image),
                    lambda db: service.upload(db, owner, EvidenceType.SELFIE, image))
    assert all(not isinstance(result, int) for result in outcomes)
    with Session(engine) as db:
        row = db.scalar(select(SellerVerification).where(SellerVerification.user_id == owner))
        assert db.scalar(select(func.count()).select_from(SellerEvidence).where(
            SellerEvidence.verification_id == row.id)) == 1
    assert len(list(service.storage.root.iterdir())) == 1


def test_concurrent_submit_blocks_late_evidence_changes(world):
    service, owner, _ = world
    call(lambda db: service.start_or_submit(db, owner, "start"))
    image = sanitize_image(image_bytes(), "proof.png", "image/png")
    for kind in EvidenceType:
        call(lambda db: service.upload(db, owner, kind, image))
    outcomes = race(lambda db: service.start_or_submit(db, owner, "submit"),
                    lambda db: service.upload(db, owner, EvidenceType.SELFIE, image))
    assert not isinstance(outcomes[0], int)
    assert outcomes[1] == 409 or outcomes[1].status.value == "PENDING"
    assert call(lambda db: service.own(db, owner)).status.value == "UNDER_REVIEW"
