"""Phase 14 synthetic scope and dependency-ordered cleanup."""
from sqlalchemy import delete, select
from app.models import Conversation, Deal, Offer
from tests.fixtures.conversations import seed_chat_world, cleanup_chat_world


def seed_offer_world(db, count=5):
    world = seed_chat_world(db, count=count)
    conversations = [Conversation(buyer_user_id=world.buyer.id, seller_user_id=world.seller.id,
                                  product_listing_id=p.id) for p in world.products]
    conversations.append(Conversation(buyer_user_id=world.outsider.id, seller_user_id=world.seller.id,
                                      product_listing_id=world.products[0].id))
    db.add_all(conversations)
    db.flush()
    return world, [c.public_ref for c in conversations]


def cleanup_offer_world(db, world):
    product_ids = [p.id for p in world.products]
    db.execute(delete(Deal).where(Deal.product_listing_id.in_(product_ids)))
    # A counter's timestamp is nondecreasing; delete actual leaves, not timestamp assumptions.
    while True:
        rows = db.execute(select(Offer.id, Offer.parent_offer_id).where(Offer.product_listing_id.in_(product_ids))).all()
        if not rows:
            break
        parents = {row.parent_offer_id for row in rows if row.parent_offer_id}
        leaves = [row.id for row in rows if row.id not in parents]
        if not leaves:
            raise AssertionError("Synthetic offer cycle; refusing broad cleanup.")
        db.execute(delete(Offer).where(Offer.id.in_(leaves), Offer.product_listing_id.in_(product_ids)))
    cleanup_chat_world(db, world)
