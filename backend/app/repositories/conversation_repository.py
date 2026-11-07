"""Participant-scoped chat queries. Services own locks, policy and final commits."""
from datetime import datetime

from sqlalchemy import and_, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.common.chat import CursorPosition
from app.models import Conversation, ProductListing, User
from app.models.seller_verification import SellerVerification, VerificationStatus
from app.repositories.product_card_projection import public_product_identity_statement


class ConversationRepository:
    @staticmethod
    def membership(actor_id: str):
        return or_(Conversation.buyer_user_id == actor_id, Conversation.seller_user_id == actor_id)

    def account_state(self, db: Session, actor_id: str):
        return db.execute(select(User.account_status, User.email_verified, User.phone_verified)
                          .where(User.id == actor_id)).first()

    def public_product(self, db: Session, slug: str, *, current: bool = False):
        statement = public_product_identity_statement().add_columns(
            ProductListing.seller_user_id,
        ).where(ProductListing.public_slug == slug)
        if current:
            statement = statement.with_for_update(read=True)
        return db.execute(statement).first()

    def seller_verified_current(self, db: Session, seller_id: str) -> bool:
        # The caller already holds the seller User lock. This separate current
        # read also excludes a stale EXISTS subquery from an earlier auth snapshot.
        return db.scalar(select(SellerVerification.id).where(
            SellerVerification.user_id == seller_id,
            SellerVerification.status == VerificationStatus.VERIFIED,
        ).limit(1).with_for_update(read=True)) is not None

    def existing_for_update(self, db: Session, buyer_id: str, seller_id: str, product_id: str):
        return db.scalar(select(Conversation).where(
            Conversation.buyer_user_id == buyer_id,
            Conversation.seller_user_id == seller_id,
            Conversation.product_listing_id == product_id,
        ).with_for_update().execution_options(populate_existing=True))

    def create(self, db: Session, buyer_id: str, seller_id: str, product_id: str,
               at: datetime) -> Conversation:
        row = Conversation(buyer_user_id=buyer_id, seller_user_id=seller_id,
                           product_listing_id=product_id, created_at=at, activity_at=at)
        db.add(row)
        db.flush()
        return row

    def owned(self, db: Session, actor_id: str, reference: str, *, for_update: bool = False):
        statement = (select(Conversation, ProductListing.public_slug)
                     .join(ProductListing, ProductListing.id == Conversation.product_listing_id)
                     .where(Conversation.public_ref == reference, self.membership(actor_id)))
        if for_update:
            # Lock only the conversation with a separate identity query. The
            # historical product reference is immutable and needs no write lock.
            conversation = db.scalar(select(Conversation).where(
                Conversation.public_ref == reference, self.membership(actor_id),
            ).with_for_update().execution_options(populate_existing=True))
            if conversation is None:
                return None
            slug = db.scalar(select(ProductListing.public_slug).where(
                ProductListing.id == conversation.product_listing_id,
            ))
            return conversation, slug
        return db.execute(statement.execution_options(populate_existing=True)).first()

    def page_statement(self, actor_id: str, limit: int, position: CursorPosition | None):
        # An OR over buyer/seller can sort all of a user's history. Each disjoint
        # role instead performs an indexed seek and contributes at most limit+1
        # rows, bounding the merged sort and product lookups to at most 102 rows.
        branches = []
        for role, column, index in (
            ("buyer", Conversation.buyer_user_id, "ix_conversations_buyer_activity"),
            ("seller", Conversation.seller_user_id, "ix_conversations_seller_activity"),
        ):
            branch = select(
                Conversation.public_ref.label("conversation_ref"),
                Conversation.product_listing_id, Conversation.created_at, Conversation.activity_at,
                literal(role).label("role"),
            ).where(column == actor_id)
            if position is not None:
                branch = branch.where(or_(
                    Conversation.activity_at < position.value,
                    and_(Conversation.activity_at == position.value,
                         Conversation.public_ref < position.reference),
                ))
            bounded = (branch.with_hint(Conversation, f"FORCE INDEX ({index})", dialect_name="mysql")
                       .order_by(Conversation.activity_at.desc(), Conversation.public_ref.desc())
                       .limit(limit + 1).subquery(role + "_conversations"))
            branches.append(select(bounded))
        candidates = union_all(*branches).subquery("participant_conversations")
        return (select(
            candidates.c.conversation_ref, ProductListing.public_slug.label("product_slug"),
            candidates.c.role, candidates.c.created_at, candidates.c.activity_at,
        ).select_from(candidates)
         .join(ProductListing, ProductListing.id == candidates.c.product_listing_id)
         .order_by(candidates.c.activity_at.desc(), candidates.c.conversation_ref.desc())
         .limit(limit + 1))

    def page(self, db: Session, actor_id: str, limit: int, position: CursorPosition | None):
        return db.execute(self.page_statement(actor_id, limit, position)).mappings().all()
