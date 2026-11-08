"""Private agreement queries; no commits or independent price updates."""
from sqlalchemy import select
from app.models import Conversation, Deal, Offer, ProductListing
from app.repositories.offer_repository import membership, page_candidates


class DealRepository:
    def for_product(self, db, product_id):
        return db.scalar(select(Deal).where(Deal.product_listing_id == product_id)
                         .with_for_update().execution_options(populate_existing=True))

    def create(self, db, offer, product, now):
        row = Deal(accepted_offer_id=offer.id, product_listing_id=product.id, agreed_at=now,
                   product_title_snapshot=product.title, product_condition_snapshot=product.condition)
        db.add(row)
        db.flush()
        return row

    def projection(self):
        return (select(Deal, Offer, Conversation, ProductListing.public_slug)
                .join(Offer, Offer.id == Deal.accepted_offer_id)
                .join(Conversation, Conversation.id == Offer.conversation_id)
                .join(ProductListing, ProductListing.id == Deal.product_listing_id))

    def view(self, db, actor, reference):
        return db.execute(self.projection().where(Deal.public_ref == reference, membership(actor))).first()

    def for_offer(self, db, actor, offer_id):
        # Acceptance owns the context locks; recover concurrently committed outcomes.
        return db.execute(self.projection().where(Deal.accepted_offer_id == offer_id, membership(actor))
                          .with_for_update(read=True).execution_options(populate_existing=True)).first()

    def page(self, db, actor, query, position, now):
        candidates = page_candidates(Deal, Deal.agreed_at, actor, query, position, now)
        return db.execute(self.projection().join(candidates, candidates.c.id == Deal.id)
                          .order_by(Deal.agreed_at.desc(), Deal.public_ref.desc())).all()
