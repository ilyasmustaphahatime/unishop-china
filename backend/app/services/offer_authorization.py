"""Offer membership and current eligibility without route-to-route dependencies."""
from sqlalchemy import select
from app.common.enums import AccountStatus
from app.common.offers import OfferError
from app.core.authorization import lock_active_user
from app.models import Conversation, ProductListing, User
from app.repositories.catalog_repository import CatalogAuditRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.offer_repository import membership
from app.repositories.user_repository import UserRepository


def actor_role(conversation, actor):
    if actor == conversation.buyer_user_id:
        return "BUYER"
    if actor == conversation.seller_user_id:
        return "SELLER"
    raise OfferError()


def require_actor(db, actor, *, current=False):
    statement = select(User.account_status).where(User.id == actor)
    if current:
        statement = statement.with_for_update(read=True)
    if db.scalar(statement) != AccountStatus.ACTIVE:
        raise OfferError("Account unavailable.", 401)


def owned_conversation(db, actor, reference):
    row = db.scalar(select(Conversation).where(Conversation.public_ref == reference, membership(actor)))
    if row is None:
        raise OfferError()
    return row


def lock_context(db, actor, conversation):
    # All mutations: sorted users -> product -> catalog eligibility guard ->
    # conversation -> offer -> competing offers. Never acquire users after product.
    users = {}
    for user_id in sorted((conversation.buyer_user_id, conversation.seller_user_id)):
        user = UserRepository().get_by_id_for_update(db, user_id)
        if user is None:
            raise OfferError("Participant unavailable.", 409)
        users[user_id] = user
    lock_active_user(db, actor)
    if conversation.buyer_user_id == conversation.seller_user_id:
        raise OfferError("Self-offers are not permitted.", 409)
    product = db.scalar(select(ProductListing).where(ProductListing.id == conversation.product_listing_id)
                        .with_for_update().execution_options(populate_existing=True))
    if product is None or product.seller_user_id != conversation.seller_user_id:
        raise OfferError("Listing unavailable.", 409)
    CatalogAuditRepository().lock_writes(db)
    repo = ConversationRepository()
    eligible = (repo.seller_verified_current(db, conversation.seller_user_id)
                and repo.public_product(db, product.public_slug, current=True) is not None)
    conversation = db.scalar(select(Conversation).where(Conversation.id == conversation.id, membership(actor))
                             .with_for_update().execution_options(populate_existing=True))
    if conversation is None:
        raise OfferError()
    return conversation, product, users, eligible


def require_trading_eligibility(actor, users, eligible):
    for user in users.values():
        if user.account_status != AccountStatus.ACTIVE:
            raise OfferError("Participant unavailable.", 409)
        if not user.email_verified or not user.phone_verified:
            raise OfferError("Verified participants required.", 403 if user.id == actor else 409)
    if not eligible:
        raise OfferError("Listing unavailable.", 409)
