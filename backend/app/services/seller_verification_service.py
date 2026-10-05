from contextlib import contextmanager
from datetime import timedelta
import hashlib
import hmac
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AccountStatus, UserRoleType
from app.common.datetime_utils import as_utc
from app.models import User, UserRole
from app.models.base import utc_now
from app.models.seller_verification import (
    SellerVerification, SellerEvidence, SellerVerificationAudit, VerificationStatus, EvidenceType,
)
from app.repositories.seller_verification_repository import SellerVerificationRepository
from app.schemas.seller_verification import VerificationResponse, EvidenceSummary
from app.services.storage_service import StorageProvider, CleanImage

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class SellerVerificationService:
    def __init__(self, storage: StorageProvider, *, challenge_lifetime_minutes=10, now_provider=utc_now):
        self.storage = storage
        self.repo = SellerVerificationRepository()
        self.challenge_lifetime = timedelta(minutes=challenge_lifetime_minutes)
        self.now = now_provider

    @staticmethod
    @contextmanager
    def transaction(db: Session):
        try:
            if db.in_transaction():
                with db.begin_nested():
                    yield
                db.commit()
            else:
                with db.begin():
                    yield
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def lock_user(db: Session, user_id: str, *, eligible=False) -> User:
        user = db.scalar(select(User).where(User.id == user_id).with_for_update()
                         .execution_options(populate_existing=True))
        if user is None or user.account_status != AccountStatus.ACTIVE:
            raise VerificationError("Account unavailable.", 401)
        if eligible and (not user.email_verified or not user.phone_verified):
            raise VerificationError("Verify both email and phone before continuing.", 403)
        return user

    @staticmethod
    def admin(db: Session, actor_id: str):
        role = db.scalar(select(UserRole.id).where(
            UserRole.user_id == actor_id, UserRole.role == UserRoleType.ADMIN).with_for_update())
        if role is None:
            raise VerificationError("Administrator access required.", 403)

    @staticmethod
    def audit(db: Session, row: SellerVerification, actor_id: str, event: str):
        db.add(SellerVerificationAudit(verification_id=row.id, actor_id=actor_id, event=event))

    def response(self, db: Session, row: SellerVerification) -> VerificationResponse:
        return VerificationResponse(
            review_reference=row.review_reference, status=row.status,
            handwritten_challenge=row.handwritten_challenge,
            challenge_expires_at=as_utc(row.challenge_expires_at),
            rejection_reason=row.rejection_reason, submitted_at=row.submitted_at,
            reviewed_at=row.reviewed_at, created_at=row.created_at,
            evidence=[EvidenceSummary(evidence_type=e.evidence_type, mime_type=e.mime_type, size=e.size)
                      for e in self.repo.evidence(db, row.id)])

    def own(self, db: Session, actor_id: str):
        with self.transaction(db):
            self.lock_user(db, actor_id)
            row = self.repo.latest(db, actor_id)
            return self.response(db, row) if row else None

    def start_or_submit(self, db: Session, actor_id: str, action: str):
        old_key = None
        with self.transaction(db):
            self.lock_user(db, actor_id, eligible=True)
            row = self.repo.latest(db, actor_id)
            if action == "start":
                if row and row.status != VerificationStatus.REJECTED:
                    raise VerificationError("A verification request already exists.")
                row = SellerVerification(user_id=actor_id, challenge_expires_at=self.now() + self.challenge_lifetime)
                db.add(row)
                db.flush()
                self.audit(db, row, actor_id, "START")
            elif action == "renew_challenge":
                if row is None or row.status != VerificationStatus.PENDING:
                    raise VerificationError("Only a pending draft can renew its challenge.")
                row.handwritten_challenge = secrets.token_hex(6).upper()
                row.challenge_expires_at = self.now() + self.challenge_lifetime
                # Evidence of the old challenge must never satisfy a new submission.
                previous = next((e for e in self.repo.evidence(db, row.id)
                                 if e.evidence_type == EvidenceType.HANDWRITTEN_CODE), None)
                if previous:
                    old_key = previous.storage_key
                    db.delete(previous)
                self.audit(db, row, actor_id, "CHALLENGE_RENEWED")
            elif action == "submit":
                if row is None or row.status != VerificationStatus.PENDING:
                    raise VerificationError("Only a pending draft can be submitted.")
                self.require_live_challenge(row)
                if {e.evidence_type for e in self.repo.evidence(db, row.id)} != set(EvidenceType):
                    raise VerificationError("All three evidence images are required.")
                row.status = VerificationStatus.UNDER_REVIEW
                row.submitted_at = self.now()
                self.audit(db, row, actor_id, "SUBMISSION")
            else:
                raise VerificationError("Invalid verification action.", 422)
            db.flush()
            result = self.response(db, row)
        if old_key:
            try:
                self.storage.delete(old_key)
            except Exception:
                logger.error("seller_evidence_cleanup_required")
        logger.info("seller_verification_event=%s", action)
        return result

    def require_live_challenge(self, row: SellerVerification):
        if as_utc(row.challenge_expires_at) <= as_utc(self.now()):
            raise VerificationError("Challenge expired. Renew it and upload a new handwritten-code image.")

    def upload(self, db: Session, actor_id: str, kind: EvidenceType, image: CleanImage,
               challenge: str | None = None):
        key = None
        old_key = None
        try:
            with self.transaction(db):
                self.lock_user(db, actor_id, eligible=True)
                row = self.repo.latest(db, actor_id)
                if row is None or row.status != VerificationStatus.PENDING:
                    raise VerificationError("Only a pending draft can receive evidence.")
                if kind == EvidenceType.HANDWRITTEN_CODE:
                    self.require_live_challenge(row)
                    if not challenge or not hmac.compare_digest(challenge, row.handwritten_challenge):
                        raise VerificationError("Challenge changed. Reload before uploading handwritten evidence.")
                existing = next((e for e in self.repo.evidence(db, row.id) if e.evidence_type == kind), None)
                key = self.storage.upload(image.data)
                if existing:
                    old_key = existing.storage_key
                    existing.storage_key, existing.file_hash = key, image.file_hash
                    existing.mime_type, existing.size = image.mime_type, len(image.data)
                else:
                    db.add(SellerEvidence(verification_id=row.id, evidence_type=kind, storage_key=key,
                                          file_hash=image.file_hash, mime_type=image.mime_type, size=len(image.data)))
                self.audit(db, row, actor_id, "UPLOAD")
                db.flush()
                result = self.response(db, row)
        except Exception:
            if key:
                try:
                    self.storage.delete(key)
                except Exception:
                    logger.error("seller_evidence_cleanup_required")
            raise
        if old_key:
            try:
                self.storage.delete(old_key)
            except Exception:
                logger.error("seller_evidence_cleanup_required")
        logger.info("seller_verification_event=upload")
        return result

    def review(self, db: Session, actor_id: str, reference: str, reason: str | None):
        with self.transaction(db):
            # Determine owner without trusting the client; then lock all users in a fixed order.
            owner = db.scalar(select(SellerVerification.user_id).where(
                SellerVerification.review_reference == reference))
            if owner is None:
                raise VerificationError("Verification not found.", 404)
            for user_id in sorted({owner, actor_id}):
                self.lock_user(db, user_id, eligible=(user_id == owner))
            self.admin(db, actor_id)
            if owner == actor_id:
                raise VerificationError("Self-review is not permitted.", 403)
            row = self.repo.by_reference(db, reference)
            if row.status != VerificationStatus.UNDER_REVIEW:
                raise VerificationError("Only submitted requests can be reviewed.")
            if {e.evidence_type for e in self.repo.evidence(db, row.id)} != set(EvidenceType):
                raise VerificationError("Evidence is incomplete.")
            row.status = VerificationStatus.REJECTED if reason is not None else VerificationStatus.VERIFIED
            row.rejection_reason = reason
            row.reviewed_by = actor_id
            row.reviewed_at = utc_now()
            # Verification is separate from role provisioning/listing permissions.
            self.audit(db, row, actor_id, "REJECTION" if reason is not None else "APPROVAL")
            db.flush()
            result = self.response(db, row)
        logger.info("seller_verification_event=%s", "rejection" if reason is not None else "approval")
        return result

    def list_pending(self, db: Session, actor_id: str, offset: int):
        with self.transaction(db):
            self.lock_user(db, actor_id)
            self.admin(db, actor_id)
            rows = list(db.scalars(select(SellerVerification).where(
                SellerVerification.status == VerificationStatus.UNDER_REVIEW)
                .order_by(SellerVerification.submitted_at, SellerVerification.id)
                .offset(offset).limit(50).with_for_update().execution_options(populate_existing=True)))
            return [self.response(db, row) for row in rows]

    def authorized_evidence(self, db: Session, actor_id: str, reference: str, kind: EvidenceType):
        with self.transaction(db):
            _, evidence = self._locked_evidence(db, actor_id, reference, kind)
            return evidence.storage_key, evidence.mime_type, evidence.file_hash

    def _locked_evidence(self, db: Session, actor_id: str, reference: str, kind: EvidenceType):
        self.lock_user(db, actor_id)
        row = self.repo.by_reference(db, reference)
        if row is None:
            raise VerificationError("Evidence not found.", 404)
        if row.user_id != actor_id:
            try:
                self.admin(db, actor_id)
            except VerificationError:
                raise VerificationError("Evidence not found.", 404) from None
        evidence = next((e for e in self.repo.evidence(db, row.id) if e.evidence_type == kind), None)
        if evidence is None:
            raise VerificationError("Evidence not found.", 404)
        return row, evidence

    def read_evidence(self, db: Session, actor_id: str, ticket: str) -> tuple[bytes, str]:
        """Authorize, validate and commit the read audit before releasing any bytes.

        Keep the verification/evidence locks through the bounded storage read so
        a replacement or review cannot invalidate the checked metadata mid-read.
        A failed operation consumes the one-use ticket; obtain a new grant to retry.
        """
        with self.transaction(db):
            key, reference, kind = self.storage.redeem(ticket, actor_id)
            row, evidence = self._locked_evidence(db, actor_id, reference, EvidenceType(kind))
            if evidence.storage_key != key:
                raise VerificationError("Evidence not found.", 404)
            data = self.storage.read(key)
            if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), evidence.file_hash):
                raise VerificationError("Evidence unavailable.", 503)
            mime = evidence.mime_type
            self.audit(db, row, actor_id, "EVIDENCE_READ")
            db.flush()
        return data, mime
