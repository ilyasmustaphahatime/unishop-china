"""Proposal lifecycle; one transaction owns agreement, archival and cancellation."""
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from sqlalchemy.exc import IntegrityError

from app.common.datetime_utils import as_utc
from app.common.offers import OfferError, OfferPosition, close_offer, effective_status, validate_ref, validate_input
from app.core.config import settings
from app.core.offer_limits import consume_offer_limit
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.repositories.deal_repository import DealRepository
from app.repositories.offer_repository import OfferRepository
from app.schemas.offer import CounterOffer, OfferCreate, OfferListQuery, OfferPage, OfferResponse
from app.services.offer_authorization import actor_role, lock_context, owned_conversation, require_actor, require_trading_eligibility
from app.services.offer_cursor import OfferCursor


def conflict_guard(operation):
    @wraps(operation)
    def run(*args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except IntegrityError as error:
            names = ("uq_offers_client_id", "uq_offers_pending", "uq_offers_parent", "uq_offers_public_ref",
                     "uq_deals_offer", "uq_deals_product", "uq_deals_public_ref")
            if getattr(error.orig, "args", (None,))[0] == 1062 and any(n in str(error.orig) for n in names):
                raise OfferError("Operation conflicts with current state.", 409) from None
            raise
    return run


def offer_view(view, actor, now):
    row, conversation, slug, parent, child, deal = view
    status = effective_status(row, now)
    expired = status == "EXPIRED"
    return OfferResponse(offer_ref=row.public_ref, conversation_ref=conversation.public_ref, product_slug=slug,
        role=actor_role(conversation, actor).lower(), proposer_role=row.proposer_role.lower(),
        amount=format(row.amount, ".2f"), currency="CNY", status=status, created_at=as_utc(row.created_at),
        expires_at=as_utc(row.expires_at), closed_at=as_utc(row.expires_at if expired else row.closed_at) if expired or row.closed_at else None,
        closed_by_role=row.closed_by_role.lower() if row.closed_by_role else None,
        closure_reason="EXPIRED" if expired else row.closure_reason, parent_offer_ref=parent,
        counteroffer_ref=child, deal_ref=deal)


class OfferService:
    def __init__(self, db, config=settings):
        self.db, self.config, self.repo = db, config, OfferRepository()

    def prepare(self, actor, action):
        require_actor(self.db, actor, current=action == "read")
        consume_offer_limit(action, actor)

    validate = staticmethod(validate_input)

    def create(self, actor, body):
        self.prepare(actor, "write")
        body = self.validate(body, OfferCreate)
        return self._propose(self.db, actor, body, None)

    def counter(self, actor, reference, body):
        self.prepare(actor, "write")
        self.reference(reference)
        body = self.validate(body, CounterOffer)
        return self._propose(self.db, actor, body, reference)

    @staticmethod
    def reference(value):
        try:
            return validate_ref(value, "of")
        except ValueError:
            raise OfferError("Invalid offer reference.", 422) from None

    def _found(self, actor, reference):
        found = self.repo.owned(self.db, actor, reference)
        if found is None:
            raise OfferError()
        return found

    @conflict_guard
    @retry_deadlock
    def _propose(self, db, actor, body, parent_ref):
        with transaction(db):
            parent = self._found(actor, parent_ref) if parent_ref else None
            if parent:
                view = self.repo.view(db, actor, parent_ref)
                conversation = view[1]
            else:
                conversation = owned_conversation(db, actor, body.conversation_ref)
            conversation, product, users, eligible = lock_context(db, actor, conversation)
            role = actor_role(conversation, actor)
            if parent:
                parent = self.repo.locked(db, parent.id)
                if role == parent.proposer_role:
                    raise OfferError("Only the recipient can counter.", 403)
            elif role != "BUYER":
                raise OfferError("Only the buyer can start an offer.", 403)
            existing = self.repo.by_client(db, conversation.id, role, body.client_offer_id)
            if existing is not None:
                if existing.amount != Decimal(body.amount) or existing.parent_offer_id != (parent.id if parent else None):
                    raise OfferError("Offer identifier already used.", 409)
                result = offer_view(self.repo.view(db, actor, existing.public_ref, current=True), actor, utc_now().replace(tzinfo=None))
                return result, False
            require_trading_eligibility(actor, users, eligible)
            if DealRepository().for_product(db, product.id) is not None:
                raise OfferError("Listing unavailable.", 409)
            now = utc_now().replace(tzinfo=None)
            if parent:
                self._pending(parent, now)
                close_offer(parent, "COUNTERED", now, role)
            else:
                pending = self.repo.pending(db, conversation.id)
                now = utc_now().replace(tzinfo=None)
                if pending:
                    if effective_status(pending, now) != "EXPIRED":
                        raise OfferError("A pending offer already exists.", 409)
                    close_offer(pending, "EXPIRED", now)
            db.flush()  # Release the old unique pending slot before inserting the new proposal.
            row = self.repo.create(db, conversation_id=conversation.id, product_listing_id=product.id,
                parent_offer_id=parent.id if parent else None, proposer_role=role, amount=Decimal(body.amount),
                currency="CNY", client_offer_id=body.client_offer_id, status="PENDING", created_at=now,
                expires_at=now + timedelta(hours=24))
            result = offer_view(self.repo.view(db, actor, row.public_ref, current=True), actor, now)
        return result, True

    @staticmethod
    def _pending(row, now):
        if effective_status(row, now) != "PENDING":
            raise OfferError("Offer is no longer pending.", 409)

    def transition(self, actor, reference, action):
        self.prepare(actor, "write")
        self.reference(reference)
        if action not in {"accept", "reject", "withdraw"}:
            raise OfferError("Invalid offer action.", 422)
        return self._transition(self.db, actor, reference, action)

    @conflict_guard
    @retry_deadlock
    def _transition(self, db, actor, reference, action):
        from app.services.deal_service import deal_view

        with transaction(db):
            self._found(actor, reference)
            conversation = self.repo.view(db, actor, reference)[1]
            conversation, product, users, eligible = lock_context(db, actor, conversation)
            row = self.repo.locked(db, self._found(actor, reference).id)
            role = actor_role(conversation, actor)
            if (action == "withdraw") != (role == row.proposer_role):
                raise OfferError("This action is not permitted.", 403)
            target = {"accept": "ACCEPTED", "reject": "REJECTED", "withdraw": "WITHDRAWN"}[action]
            deals = DealRepository()
            if row.status == target and row.closed_by_role == role:
                if action == "accept":
                    view = deals.for_offer(db, actor, row.id)
                    if view is None:
                        raise OfferError("Agreement unavailable.", 503)
                    return deal_view(view, actor)
                return offer_view(self.repo.view(db, actor, reference, current=True), actor, utc_now().replace(tzinfo=None))
            if action == "accept":
                require_trading_eligibility(actor, users, eligible)
                if deals.for_product(db, product.id) is not None:
                    raise OfferError("Listing unavailable.", 409)
            now = utc_now().replace(tzinfo=None)
            self._pending(row, now)
            close_offer(row, target, now, role)
            db.flush()
            if action == "accept":
                deals.create(db, row, product, now)
                product.status = "ARCHIVED"
                self.repo.close_product_pending(db, product.id, now)
                result = deal_view(deals.for_offer(db, actor, row.id), actor)
            else:
                result = offer_view(self.repo.view(db, actor, reference, current=True), actor, now)
        return result

    def get(self, actor, reference):
        self.prepare(actor, "read")
        self.reference(reference)
        view = self.repo.view(self.db, actor, reference)
        if view is None:
            raise OfferError()
        return offer_view(view, actor, utc_now().replace(tzinfo=None))

    def list(self, actor, query):
        self.prepare(actor, "read")
        query = self.validate(query, OfferListQuery)
        if query.conversation_ref:
            owned_conversation(self.db, actor, query.conversation_ref)
        codec = OfferCursor(self.config, actor, "offers", query)
        position = codec.decode(query.cursor) if query.cursor is not None else None
        now = utc_now().replace(tzinfo=None)
        rows = self.repo.page(self.db, actor, query, position, now)
        emitted = rows[:query.limit]
        cursor = codec.encode(OfferPosition(emitted[-1][0].created_at, emitted[-1][0].public_ref)) if len(rows) > query.limit else None
        return OfferPage(items=[offer_view(row, actor, now) for row in emitted], next_cursor=cursor)
