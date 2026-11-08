"""Scoped offer persistence. Caller owns transaction and account/product locks."""
from sqlalchemy import and_, case, or_, select, union_all
from sqlalchemy.orm import aliased

from app.common.offers import close_offer
from app.models import Conversation, Deal, Offer, ProductListing


def membership(actor):
    return or_(Conversation.buyer_user_id == actor, Conversation.seller_user_id == actor)


def status_expression(now):
    return case((and_(Offer.status == "PENDING", Offer.expires_at <= now), "EXPIRED"), else_=Offer.status)


def page_candidates(model, time_column, actor, query, position, now):
    """Two participant-filtered branches; bound the merge and final projection."""
    branches = []
    for role, column in (("buyer", Conversation.buyer_user_id), ("seller", Conversation.seller_user_id)):
        if query.role is not None and role != query.role:
            continue
        # MySQL otherwise may scan global offers in time order before checking
        # membership. Start from this actor's indexed conversations instead.
        index = "ix_conversations_" + role + "_activity"
        statement = (select(model.id, time_column.label("at"), model.public_ref.label("ref"))
            .select_from(Conversation).join(Offer, Offer.conversation_id == Conversation.id)
            .where(column == actor).prefix_with("STRAIGHT_JOIN", dialect="mysql")
            .with_hint(Conversation, f"FORCE INDEX ({index})", dialect_name="mysql")
            .with_hint(Offer, "FORCE INDEX (ix_offers_conversation_created)", dialect_name="mysql"))
        if model is Deal:
            statement = statement.join(Deal, Deal.accepted_offer_id == Offer.id)
        if query.conversation_ref is not None:
            statement = statement.where(Conversation.public_ref == query.conversation_ref)
        if model is Offer and query.status is not None:
            statement = statement.where(status_expression(now) == query.status)
        if position:
            statement = statement.where(or_(time_column < position.value,
                and_(time_column == position.value, model.public_ref < position.reference)))
        branch = statement.order_by(time_column.desc(), model.public_ref.desc()).limit(query.limit + 1).subquery()
        branches.append(select(branch))
    combined = union_all(*branches).subquery()
    return (select(combined.c.id).order_by(combined.c.at.desc(), combined.c.ref.desc())
            .limit(query.limit + 1).subquery())


class OfferRepository:
    def owned(self, db, actor, reference):
        return db.scalar(select(Offer).join(Conversation, Conversation.id == Offer.conversation_id)
                         .where(Offer.public_ref == reference, membership(actor))
                         .execution_options(populate_existing=True))

    def locked(self, db, offer_id):
        return db.scalar(select(Offer).where(Offer.id == offer_id).with_for_update()
                         .execution_options(populate_existing=True))

    def by_client(self, db, conversation_id, role, client_id):
        return db.scalar(select(Offer).where(Offer.conversation_id == conversation_id,
                         Offer.proposer_role == role, Offer.client_offer_id == client_id)
                         .with_for_update().execution_options(populate_existing=True))

    def pending(self, db, conversation_id):
        return db.scalar(select(Offer).where(Offer.conversation_id == conversation_id,
                         Offer.active_slot == 1).with_for_update().execution_options(populate_existing=True))

    def create(self, db, **values):
        row = Offer(**values)
        db.add(row)
        db.flush()
        return row

    def projection(self):
        parent, child = aliased(Offer), aliased(Offer)
        return (select(Offer, Conversation, ProductListing.public_slug, parent.public_ref, child.public_ref, Deal.public_ref)
                .join(Conversation, Conversation.id == Offer.conversation_id)
                .join(ProductListing, ProductListing.id == Offer.product_listing_id)
                .outerjoin(parent, parent.id == Offer.parent_offer_id)
                .outerjoin(child, child.parent_offer_id == Offer.id)
                .outerjoin(Deal, Deal.accepted_offer_id == Offer.id))

    def view(self, db, actor, reference, *, current=False):
        statement = self.projection().where(Offer.public_ref == reference, membership(actor))
        if current:
            # Mutations already hold the product/context locks. A locking read
            # sees committed retry outcomes beyond an earlier REPEATABLE READ snapshot.
            statement = statement.with_for_update(read=True)
        return db.execute(statement.execution_options(populate_existing=True)).first()

    def page(self, db, actor, query, position, now):
        candidates = page_candidates(Offer, Offer.created_at, actor, query, position, now)
        return db.execute(self.projection().join(candidates, candidates.c.id == Offer.id)
                          .order_by(Offer.created_at.desc(), Offer.public_ref.desc())
                          .execution_options(populate_existing=True)).all()

    def close_product_pending(self, db, product_id, now):
        """Transaction-neutral archival hook. Lock product first; no user/conversation locks here."""
        rows = db.scalars(select(Offer).where(Offer.product_listing_id == product_id, Offer.status == "PENDING")
                          .order_by(Offer.public_ref).with_for_update().execution_options(populate_existing=True))
        for row in rows:
            close_offer(row, "EXPIRED" if row.expires_at <= now else "CANCELLED", now)
        db.flush()
