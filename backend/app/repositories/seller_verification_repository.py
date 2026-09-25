from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.seller_verification import SellerVerification, SellerEvidence


class SellerVerificationRepository:
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
