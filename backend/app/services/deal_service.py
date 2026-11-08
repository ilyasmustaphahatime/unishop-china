"""Read-only private agreements; prices derive only from accepted proposals."""
from app.common.datetime_utils import as_utc
from app.common.offers import OfferError, OfferPosition, validate_ref, validate_input
from app.core.config import settings
from app.core.offer_limits import consume_offer_limit
from app.models.base import utc_now
from app.repositories.deal_repository import DealRepository
from app.schemas.deal import DealPage, DealResponse
from app.schemas.offer import DealListQuery
from app.services.offer_authorization import actor_role, owned_conversation, require_actor
from app.services.offer_cursor import OfferCursor


def deal_view(view, actor):
    row, offer, conversation, slug = view
    if offer.status != "ACCEPTED":
        raise OfferError("Agreement unavailable.", 503)
    return DealResponse(deal_ref=row.public_ref, accepted_offer_ref=offer.public_ref,
        conversation_ref=conversation.public_ref, product_slug=slug, role=actor_role(conversation, actor).lower(),
        amount=format(offer.amount, ".2f"), currency="CNY", agreed_at=as_utc(row.agreed_at),
        product_title_snapshot=row.product_title_snapshot, product_condition_snapshot=row.product_condition_snapshot)


class DealService:
    def __init__(self, db, config=settings):
        self.db, self.config, self.repo = db, config, DealRepository()

    def prepare(self, actor):
        require_actor(self.db, actor, current=True)
        consume_offer_limit("read", actor)

    def get(self, actor, reference):
        self.prepare(actor)
        try:
            validate_ref(reference, "dl")
        except ValueError:
            raise OfferError("Invalid deal reference.", 422) from None
        view = self.repo.view(self.db, actor, reference)
        if view is None:
            raise OfferError()
        return deal_view(view, actor)

    def list(self, actor, query):
        self.prepare(actor)
        query = validate_input(query, DealListQuery)
        if query.conversation_ref:
            owned_conversation(self.db, actor, query.conversation_ref)
        codec = OfferCursor(self.config, actor, "deals", query)
        position = codec.decode(query.cursor) if query.cursor is not None else None
        rows = self.repo.page(self.db, actor, query, position, utc_now().replace(tzinfo=None))
        emitted = rows[:query.limit]
        cursor = codec.encode(OfferPosition(emitted[-1][0].agreed_at, emitted[-1][0].public_ref)) if len(rows) > query.limit else None
        return DealPage(items=[deal_view(row, actor) for row in emitted], next_cursor=cursor)
