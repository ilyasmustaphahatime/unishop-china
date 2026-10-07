from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.seller_verification import (
    SellerVerification, SellerEvidence, SellerVerificationAudit, VerificationStatus,
)


class SellerVerificationRepository:
    def owner_by_reference(self, db: Session, reference: str) -> str | None:
        # Discovery only; the service must then lock/recheck the users and request.
        return db.scalar(select(SellerVerification.user_id).where(
            SellerVerification.review_reference == reference))

    def pending_for_review(self, db: Session, offset: int) -> list[SellerVerification]:
        return list(db.scalars(select(SellerVerification).where(
            SellerVerification.status == VerificationStatus.UNDER_REVIEW)
            .order_by(SellerVerification.submitted_at, SellerVerification.id)
            .offset(offset).limit(50).with_for_update().execution_options(populate_existing=True)))

    def has_verified_attempt(self, db: Session, user_id: str) -> bool:
        return bool(db.scalar(select(select(SellerVerification.id).where(
            SellerVerification.user_id == user_id,
            SellerVerification.status == VerificationStatus.VERIFIED,
        ).exists())))

    def record_audit(self, db: Session, *, verification_id: str, actor_id: str, event: str) -> None:
        # Flush/commit belongs to the caller's service transaction, never this writer.
        db.add(SellerVerificationAudit(verification_id=verification_id, actor_id=actor_id, event=event))

    def latest(self, db: Session, user_id: str) -> SellerVerification | None:
        return db.scalar(select(SellerVerification).where(SellerVerification.user_id == user_id)
                         .order_by(SellerVerification.created_at.desc(), SellerVerification.id.desc())
                         .limit(1).with_for_update().execution_options(populate_existing=True))

    def by_reference(self, db: Session, reference: str) -> SellerVerification | None:
        return db.scalar(select(SellerVerification).where(SellerVerification.review_reference == reference)
                         .with_for_update().execution_options(populate_existing=True))

    def evidence(self, db: Session, verification_id: str) -> list[SellerEvidence]:
        return list(db.scalars(select(SellerEvidence).where(SellerEvidence.verification_id == verification_id)
                               .order_by(SellerEvidence.evidence_type).with_for_update()
                               .execution_options(populate_existing=True)))

    def evidence_for_requests(self, db: Session, verification_ids: list[str]) -> dict[str, list[SellerEvidence]]:
        """One current, locked read for a bounded review page; no per-request query."""
        grouped: dict[str, list[SellerEvidence]] = {}
        if not verification_ids:
            return grouped
        rows = db.scalars(select(SellerEvidence).where(SellerEvidence.verification_id.in_(verification_ids))
                          .order_by(SellerEvidence.verification_id, SellerEvidence.evidence_type)
                          .with_for_update().execution_options(populate_existing=True))
        for row in rows:
            grouped.setdefault(row.verification_id, []).append(row)
        return grouped
